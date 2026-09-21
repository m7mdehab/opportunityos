"""Discovery persistence seam: maps an :class:`IngestionBatch` onto ``StorageRepository``.

This is the missing link between discovery (``opportunity.pipeline``) and the
database (``storage.repository``). ``persist_batch`` is idempotent on
``content_hash`` per opportunity identity: re-running the same batch inserts
nothing and updates nothing; a changed posting (same identity, different
``content_hash``) is written again and marked re-verified rather than
duplicated.

Identity choice
----------------
"Same identity" is taken to be ``Opportunity.id``. ``opportunity.models`` computes
this deterministically (``compute_deterministic_id``: ``f"{source}:{remote_id}"``
when the adapter has a stable remote id, else a hash of
``organization:title:raw_pointer``) and it is also the primary key of
``OpportunityRecord`` (``storage/models.py``, ``id = Column(String(64),
primary_key=True)``). Keying on ``id`` is therefore the natural, storage-enforced
identity: it is what the schema itself treats as "the same posting" across
repeated polls of the same source, independent of whether the *content* of that
posting changed. ``content_hash`` (derived from organization/title/location/
description) is deliberately used only as a *change* signal, not as the identity
key -- it is indexed but not unique in the schema, and two distinct postings can
coincidentally normalize to the same hash. ``dedup_key`` was considered and
rejected for this role: it is intentionally coarser (used for *cross-source*
duplicate clustering upstream in ``opportunity.dedupe``), so keying persistence
identity on it would collapse genuinely distinct postings from the same source
that happen to share organization/title/location.

Re-verification vocabulary
---------------------------
``storage/models.py`` already carries ``is_stale`` / ``reverified_at`` columns,
and ``opportunity/reverification.py`` (``StaleOpportunityReverifier``) already
defines *a* re-verification semantic -- but per FR-003's own finding, that
module is exercised by nothing but its own test, and its semantic is a live
HTTP reachability check (fetches the posting's URL; ``is_stale`` = the URL now
404s/410s). That semantic does not apply here: ``persist_batch`` runs against an
already-fetched, already-normalized ``IngestionBatch`` and must not perform any
further network I/O of its own. So this module does not reuse
``StaleOpportunityReverifier`` code (there is nothing here to reuse -- it is a
network client, not a rule), but it does extend the same *vocabulary* it
established: when a re-poll of a source returns the same opportunity identity
with a different ``content_hash``, that is itself a (poll-based, not
HTTP-based) re-verification signal that the posting is still live -- it
reappeared in a fresh feed pull, edited but present. So this module's rule is:
on a changed posting, set ``is_stale = False`` and ``reverified_at = now`` (UTC,
at persistence time). An unchanged posting is left untouched entirely (no
write, so ``reverified_at`` is *not* bumped on every identical poll -- only
genuine change events count as re-verification, matching the "re-running the
same batch ... updates nothing" requirement).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from opportunity.clustering import family_key as compute_opportunity_family_key
from opportunity.models import CompensationInterval, FieldProvenance, Opportunity
from opportunity.pipeline import IngestionBatch
from storage.repository import StorageRepository


@dataclass(frozen=True, slots=True)
class PersistResult:
    """Outcome of persisting one :class:`IngestionBatch` through a ``StorageRepository``.

    ``inserted_ids`` / ``unchanged_ids`` / ``updated_ids`` are ordered (batch
    iteration order) and mutually exclusive per opportunity id. ``unchanged``
    means the identical ``content_hash`` was already stored -- an idempotent
    skip, not a write. ``updated`` means the same identity reappeared with a
    different ``content_hash`` and was re-verified (see module docstring).
    """

    inserted_ids: tuple[str, ...] = ()
    unchanged_ids: tuple[str, ...] = ()
    updated_ids: tuple[str, ...] = ()

    @property
    def inserted_count(self) -> int:
        return len(self.inserted_ids)

    @property
    def unchanged_count(self) -> int:
        return len(self.unchanged_ids)

    @property
    def updated_count(self) -> int:
        return len(self.updated_ids)

    @property
    def total_processed(self) -> int:
        return self.inserted_count + self.unchanged_count + self.updated_count

    @property
    def persisted_ids(self) -> tuple[str, ...]:
        """All opportunity ids actually written this call (inserted or updated).

        Excludes ``unchanged_ids`` -- those were not written. Useful for a
        caller that wants to log or enqueue follow-up work (e.g. matching/
        notification) only for opportunities that are new or changed.
        """
        return self.inserted_ids + self.updated_ids


def _build_opp_data(opp: Opportunity, *, is_stale: bool) -> Dict[str, Any]:
    """Map an ``Opportunity`` onto the ``opp_data`` dict ``save_opportunity`` expects.

    ``country`` / ``region`` / ``geographic_scope`` are left ``None``:
    ``Opportunity`` has no dedicated structured place fields for them.
    ``geographic_eligibility`` is an *eligibility judgement* (status/reason,
    e.g. "eligible" / "excluded" / "unclear"), not a country, region, or scope
    -- mapping it onto those columns would invent data the model does not
    assert. ``raw_payload_json`` is populated from ``raw_provenance`` (the
    real acquisition-time source metadata) when present, since that is
    genuine provenance rather than an invented value.

    ``source_id`` is mapped from ``opp.source`` -- the registry source id
    (e.g. ``"himalayas"``, ``"greenhouse:cloudflare"``) that every adapter
    sets via ``source=self.source_id`` -- not from ``opp.source_id``, which
    is the *job's own remote id at that source* (e.g. a numeric Greenhouse
    job id). ``OpportunityRecord.source_id`` exists so the feed can be
    reconciled against ``GET /api/sources/health``, which keys on registry
    ids; a bare per-job number cannot be reconciled against anything. The
    remote job id is not lost by this: ``Opportunity.id`` is computed by
    ``compute_deterministic_id(source, remote_id, ...)`` (``opportunity/
    models.py``) as ``f"{source}:{remote_id}"`` whenever the adapter has a
    stable remote id, and that id is itself the persisted row's primary key
    (``"id": opp.id`` below) -- so the remote job id remains recoverable
    verbatim from the row's own id, it is just no longer duplicated into
    ``source_id``.
    """
    raw_payload_json = None
    if opp.raw_provenance is not None:
        raw_payload_json = json.dumps(asdict(opp.raw_provenance), sort_keys=True)

    # BRIEF-FR-006 A1 defect fix: map the seven work_mode/location/remote_scope
    # fields, plus compensation_min/max/currency/period derived off the existing
    # Compensation object, using the exact column-name spellings from the A1
    # report (work order A1M owns the actual DB columns/migration -- see that
    # report's return for the full list and their types; this dict simply
    # carries the same names through so A1M's storage/repository.py wiring has
    # nothing to rename). ``remote_scope_regions`` is a tuple on Opportunity but
    # the brief specifies the column as Text (JSON array), so it is JSON-encoded
    # here, matching how ``raw_payload_json`` already round-trips through JSON.
    comp = opp.compensation
    compensation_period = None
    if comp is not None and comp.interval != CompensationInterval.UNSPECIFIED:
        compensation_period = comp.interval.value

    return {
        "id": opp.id,
        "track": opp.track.value,
        "title": (opp.title or "")[:255],
        "organization": (opp.organization or "")[:255],
        "description": opp.description,
        "source_id": opp.source,
        "source_url": opp.source_url,
        "content_hash": opp.content_hash,
        "country": None,
        "region": None,
        "geographic_scope": None,
        "posted_date": opp.posted_date,
        "deadline": opp.closing_date,
        "is_stale": is_stale,
        "raw_payload_json": raw_payload_json,
        "work_mode": opp.work_mode.value,
        "work_mode_source": opp.work_mode_source,
        "location_country": opp.location_country or None,
        "location_city": opp.location_city or None,
        "location_region": opp.location_region or None,
        "remote_scope": opp.remote_scope.value,
        "remote_scope_regions": json.dumps(list(opp.remote_scope_regions)) if opp.remote_scope_regions else None,
        "compensation_min": int(round(comp.min_amount)) if comp is not None and comp.min_amount is not None else None,
        "compensation_max": int(round(comp.max_amount)) if comp is not None and comp.max_amount is not None else None,
        "compensation_currency": comp.currency if comp is not None else None,
        "compensation_period": compensation_period,
        # A2 (BRIEF-FR-006) clustering: deterministic, pure function of
        # organization + title (see opportunity.clustering.family_key). This
        # is the only field this deliverable's allowed edit to
        # opportunity/persistence.py writes; the family/member-count roll-up
        # onto opportunity_families is a separate step (see
        # opportunity.clustering.cluster_members / storage.repository's
        # families methods), not performed per-opportunity here.
        "family_key": compute_opportunity_family_key(opp),
    }


def _build_provenances(opp: Opportunity) -> List[Dict[str, Any]]:
    return [_field_provenance_to_dict(fp) for fp in opp.field_provenances]


def _field_provenance_to_dict(fp: FieldProvenance) -> Dict[str, Any]:
    return {
        "field_name": fp.field_name,
        "raw_value": fp.raw_value,
        "normalized_value": fp.normalized_value,
        "derivation_type": fp.derivation_type,
        "raw_pointer": fp.raw_pointer,
        "record_checksum": fp.record_checksum,
        "rule_id": fp.rule_id,
    }


def persist_batch(batch: IngestionBatch, repository: StorageRepository) -> PersistResult:
    """Persist every normalized opportunity in ``batch`` (+ its field provenances).

    Idempotent on ``content_hash`` per ``Opportunity.id`` (see module
    docstring for why ``id`` is the identity key): re-running the identical
    batch inserts nothing and updates nothing. A changed posting (same ``id``,
    different ``content_hash``) is written again and marked re-verified
    (``is_stale=False``, ``reverified_at=now``) rather than inserted as a
    duplicate.

    Concurrency / race window: idempotency here is enforced purely by an
    application-level lookup (``repository.get_opportunity(opp.id)``) followed
    by a conditional write -- there is no database-level uniqueness constraint
    backing it (``content_hash`` is indexed but explicitly *not* unique in
    ``storage/models.py``, and adding one is out of scope for this
    deliverable; D4 owns the only new migration in this brief). If two workers
    call ``persist_batch`` concurrently for the same source (e.g. the same
    ``poll_source`` job double-dispatched, or two overlapping polls), both can
    execute their ``get_opportunity`` lookup before either commits, both then
    take the "not found" branch, and both attempt to write the same
    opportunity id. The second writer's ``session.merge``/commit will raise an
    ``IntegrityError`` on the ``opportunities.id`` primary key, which
    propagates out of ``persist_batch`` uncaught -- the caller (see
    ``worker/handlers.py``) rolls back its session and lets the job fail/retry
    rather than silently duplicating or corrupting a row. A production fix
    would need either a real upsert (``INSERT ... ON CONFLICT``) or a
    per-source advisory lock; both are out of scope here.
    """
    inserted: list[str] = []
    unchanged: list[str] = []
    updated: list[str] = []

    if hasattr(repository, "get_opportunity_identity_state"):
        identity_state = repository.get_opportunity_identity_state([opp.id for opp in batch.opportunities])
    else:  # small test doubles from downstream integrations
        identity_state = {}
        for opp in batch.opportunities:
            existing = repository.get_opportunity(opp.id)
            if existing is not None:
                identity_state[opp.id] = existing.content_hash

    for opp in batch.opportunities:
        existing_hash = identity_state.get(opp.id)

        if opp.id not in identity_state:
            # The prefetch is an optimization, not the concurrency authority.
            # Re-read under an identity advisory lock immediately before every
            # write so a concurrent poll cannot race the primary key.
            if hasattr(repository, "lock_opportunity_identity"):
                repository.lock_opportunity_identity(opp.id)
            existing = repository.get_opportunity(opp.id)
            if existing is not None:
                existing_hash = existing.content_hash
            else:
                existing_hash = None

        if existing_hash is None:
            opp_data = _build_opp_data(opp, is_stale=False)
            provenances = _build_provenances(opp)
            repository.save_opportunity(opp_data, provenances)
            inserted.append(opp.id)
            continue

        if existing_hash == opp.content_hash:
            # Identical re-poll: idempotent skip, no write at all (so
            # reverified_at is not disturbed either).
            unchanged.append(opp.id)
            continue

        # Same identity, changed content: write the new content and mark
        # re-verified rather than inserting a duplicate row.
        if hasattr(repository, "lock_opportunity_identity"):
            repository.lock_opportunity_identity(opp.id)
        existing = repository.get_opportunity(opp.id)
        if existing is not None and existing.content_hash == opp.content_hash:
            unchanged.append(opp.id)
            continue
        opp_data = _build_opp_data(opp, is_stale=False)
        provenances = _build_provenances(opp)
        repository.save_opportunity(opp_data, provenances)

        # save_opportunity's Dict[str, Any] interface has no reverified_at
        # parameter (storage/models.py and storage/repository.py are outside
        # this deliverable's file set), so it is set directly through the
        # repository's own session/ORM handle -- no new persistence surface,
        # just the one column save_opportunity does not expose.
        record = repository.get_opportunity(opp.id)
        if record is not None:
            record.reverified_at = datetime.now(timezone.utc)
            repository.session.commit()
        updated.append(opp.id)

    return PersistResult(
        inserted_ids=tuple(inserted),
        unchanged_ids=tuple(unchanged),
        updated_ids=tuple(updated),
    )
