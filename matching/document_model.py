"""The structured CV/cover-letter document model (BRIEF-FR-006 D1, ADR-0017).

This module is the single place that turns `TruthGraph` assertions into
founder-facing prose. It never invents a sentence: every line it produces is
either (a) a pack value rendered through a `GeneratedClaim` that cites the
supporting evidence ids, or (b) an `ApprovedPhrase` used verbatim. Tailoring
is selection (which lines appear) and ordering (what order they appear in) --
never rewording. `truth/validator.py` is the sole authority on whether a
claim is admissible; nothing here second-guesses it.

Renderers (`matching/binary_export.py`) do not compose prose: they walk
`ArtifactSection.content` / `.items`, which `DocumentSection.to_artifact_section()`
below produces by flattening `DocumentItem`s that already exist -- a renderer
never builds a sentence out of pack values itself. `CompiledDocument` is the
structured intermediate that gives every rendered item an explicit,
one-to-one link to the `GeneratedClaim` that licenses it (previously this
link was an unenforced coincidence of list order between `ArtifactSection.items`
and a compiler's separate flat `claims` list).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date

from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, RelationType, VerificationStatus

from .models import ArtifactSection, GeneratedClaim, OmittedItem

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.#/-]*")

# Best-effort, read-only mirror of the leading clause of
# `truth.validator.ClaimValidator`'s `_METRIC` pattern -- never imported
# from the frozen module. This is a defensive pre-check only, used to
# decide whether a short, non-metric value (e.g. a phone number beginning
# with a bare digit run, such as a "+20" country code) is safe to render as
# its own single-value claim, never to decide whether a claim is actually
# admissible: `matching.artifact_validation.validate_artifact_claims`,
# backed by the real, frozen validator, is always the final authority and
# runs over every artifact this compiler produces before export.
_LEADING_METRIC_RE = re.compile(r"(?<![\w-])(?:[$€£]\s*)?\d+(?:[.,]\d+)?")

# Same defensive-mirror caveat as `_LEADING_METRIC_RE` above, this time for
# `truth.validator.ClaimValidator._HELD`: a planned certification whose own
# NAME contains one of these words (e.g. "Certified Group Analytics
# Architect") cannot be rendered honestly at all -- any claim naming it,
# however framed, contains a "held" word and is rejected as claiming the
# credential is already held. Never imported from the frozen module.
_HELD_WORD_RE = re.compile(r"\b(?:certified|credentialed|holds?|holding|earned|obtained|completed|awarded)\b", re.IGNORECASE)


def _terms(text: str | None) -> set[str]:
    if not text:
        return set()
    return {w.casefold() for w in _WORD_RE.findall(text)}


def _opportunity_terms(opp: Opportunity | None) -> set[str]:
    if opp is None:
        return set()
    terms = {s.casefold() for s in opp.skills}
    terms |= _terms(opp.description)
    terms |= {r.casefold() for r in opp.requirements}
    return terms


@dataclass(frozen=True, slots=True)
class DocumentItem:
    """One renderable line, mapped 1:1 to the claim that licenses it.
    `str(item)` is the rendered text -- a `DocumentItem` can be dropped
    anywhere plain claim text was rendered before."""
    claim: GeneratedClaim

    def __str__(self) -> str:
        return self.claim.text


@dataclass(frozen=True, slots=True)
class DocumentSection:
    """A structured section: a heading plus an ordered list of items, each
    item carrying the exact claim it renders, plus the items considered and
    left out (with why)."""
    section_id: str
    heading: str
    items: tuple[DocumentItem, ...] = ()
    omitted: tuple[OmittedItem, ...] = ()

    def to_artifact_section(self) -> ArtifactSection:
        texts = tuple(str(item) for item in self.items)
        assertion_ids = tuple(dict.fromkeys(
            aid for item in self.items for aid in item.claim.assertion_ids
        ))
        evidence_ids = tuple(sorted({
            eid for item in self.items for eid in item.claim.evidence_ids
        }))
        # BRIEF-FR-006 council review #2 MAJOR 5: `content` and `items` used to
        # carry the exact same text, and both exporters render `content` as a
        # paragraph AND every `items` entry as its own bullet -- every line
        # doubled. `items` is authoritative when present (it is what actually
        # carries the per-claim structure); `content` is only for sections
        # that never populate `items` at all.
        return ArtifactSection(
            section_id=self.section_id,
            heading=self.heading,
            content="" if texts else "\n".join(texts),
            items=texts,
            assertion_ids=assertion_ids,
            evidence_ids=evidence_ids,
        )

    @property
    def claims(self) -> tuple[GeneratedClaim, ...]:
        return tuple(item.claim for item in self.items)


@dataclass(frozen=True, slots=True)
class IdentityBlock:
    """Identity claims rendered as their own section (`section_id="identity"`)
    plus the resolved field values other builders (e.g. the cover letter)
    need directly, without re-scanning the graph."""
    section: DocumentSection
    name: str
    headline: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None
    location: str | None = None


@dataclass(frozen=True, slots=True)
class CompiledDocument:
    """The structured document a compiler assembles before any renderer
    runs. `flatten()` produces the `(sections, claims, omitted_items)` a
    `TailoredArtifact` needs -- the existing DOCX/PDF exporters,
    `AtsDocumentQualityHarness`, and `validate_artifact_claims` do not need
    to change shape."""
    title: str
    identity: IdentityBlock | None
    sections: tuple[DocumentSection, ...]

    def all_sections(self) -> tuple[DocumentSection, ...]:
        if self.identity is not None:
            return (self.identity.section,) + self.sections
        return self.sections

    def flatten(self) -> tuple[tuple[ArtifactSection, ...], tuple[GeneratedClaim, ...], tuple[OmittedItem, ...]]:
        sections = self.all_sections()
        artifact_sections = tuple(sec.to_artifact_section() for sec in sections)
        claims = tuple(claim for sec in sections for claim in sec.claims)
        omitted = tuple(item for sec in sections for item in sec.omitted)
        return artifact_sections, claims, omitted


# ---------------------------------------------------------------------------
# Section builders. Each takes the truth graph (and, where relevance-ordering
# applies, the opportunity) and returns a `DocumentSection`.
# ---------------------------------------------------------------------------


def build_identity_block(graph: TruthGraph) -> IdentityBlock | None:
    """Identity block: name, headline, email, phone, LinkedIn, GitHub,
    website, location -- one atomic claim per field, each citing exactly
    the evidence ids `truth.graph.TruthGraph.add_identity` already verified
    textually support that field."""
    identity = graph.identity
    if identity is None:
        return None

    field_order = (
        ("name", "identity.name"),
        ("headline", "identity.headline"),
        ("email", "identity.email"),
        ("phone", "identity.phone"),
        ("linkedin", "identity.linkedin"),
        ("github", "identity.github"),
        ("website", "identity.website"),
    )
    by_pred: dict[str, AtomicAssertion] = {
        a.predicate: a
        for a in graph.assertions.values()
        if a.subject_id == identity.id
        and a.predicate.startswith("identity.")
        and a.verification_status == VerificationStatus.VERIFIED
    }

    items: list[DocumentItem] = []
    omitted: list[OmittedItem] = []
    values: dict[str, str | None] = {}
    for field_name, predicate in field_order:
        a = by_pred.get(predicate)
        if a is None:
            values[field_name] = None
            continue
        text = str(a.value)
        values[field_name] = text
        if _LEADING_METRIC_RE.search(text):
            # E.g. a phone number written with a leading country code
            # ("+20-555-0101"): rendered on its own, this reads to
            # `ClaimValidator._validate_metric_provenance` as a bare
            # numeric claim ("20") with no verified metric backing it, and
            # is rejected -- not a content problem, a validator false
            # positive on short digit-led values. Per the work order's hard
            # stop this compiler does not touch the validator; it omits the
            # field from the rendered document instead and reports the
            # case. The value is still resolved on `IdentityBlock` for any
            # non-claim internal use.
            omitted.append(OmittedItem(
                section_id="identity",
                text=text,
                reason=(
                    "validator rejects this value as an unsupported bare metric "
                    "(known validator interaction with short digit-led values, "
                    "not a content gap -- see the work order return)"
                ),
                claim_id=f"claim-identity-{field_name}",
            ))
            continue
        items.append(DocumentItem(GeneratedClaim(
            claim_id=f"claim-identity-{field_name}",
            text=text,
            section_id="identity",
            assertion_ids=(a.id,),
            evidence_ids=a.evidence_ids,
            predicate=predicate,
            authorized_value=text,
        )))

    city = by_pred.get("identity.location_city")
    country = by_pred.get("identity.location_country")
    location_text: str | None = None
    if city is not None and country is not None:
        location_text = f"{city.value}, {country.value}"
        items.append(DocumentItem(GeneratedClaim(
            claim_id="claim-identity-location",
            text=location_text,
            section_id="identity",
            assertion_ids=(city.id, country.id),
            evidence_ids=tuple(sorted(set(city.evidence_ids) | set(country.evidence_ids))),
            predicate="identity.location",
            authorized_value=location_text,
        )))
    elif city is not None or country is not None:
        only = city if city is not None else country
        location_text = str(only.value)
        items.append(DocumentItem(GeneratedClaim(
            claim_id="claim-identity-location",
            text=location_text,
            section_id="identity",
            assertion_ids=(only.id,),
            evidence_ids=only.evidence_ids,
            predicate="identity.location",
            authorized_value=location_text,
        )))
    values["location"] = location_text

    section = DocumentSection(
        section_id="identity", heading="Contact Information", items=tuple(items), omitted=tuple(omitted),
    )
    return IdentityBlock(section=section, **values)


def build_summary_section(graph: TruthGraph, opp: Opportunity | None) -> DocumentSection:
    """Summary: select the approved-summary variant whose evidence text
    best matches the posting's requirements -- selection, never rewriting.
    Every candidate is a founder-authored `profile.approved_summary`
    assertion (`career_profile.approved_summaries`); the unselected
    variants are recorded in the omitted panel."""
    candidates = [
        a for a in graph.assertions.values()
        if a.predicate == "profile.approved_summary" and a.verification_status == VerificationStatus.VERIFIED
    ]
    if not candidates:
        return DocumentSection(section_id="summary", heading="Professional Summary")

    opp_terms = _opportunity_terms(opp)

    def _score(a: AtomicAssertion) -> int:
        return len(_terms(str(a.value)) & opp_terms)

    ranked = sorted(candidates, key=lambda a: (-_score(a), a.id))
    selected = ranked[0]
    text = str(selected.value)
    item = DocumentItem(GeneratedClaim(
        claim_id=f"claim-summary-{selected.id}",
        text=text,
        section_id="summary",
        assertion_ids=(selected.id,),
        evidence_ids=selected.evidence_ids,
        predicate="profile.approved_summary",
        authorized_value=text,
    ))
    omitted = tuple(
        OmittedItem(
            section_id="summary",
            text=str(a.value),
            reason="not the best-matching approved-summary variant for this posting",
            claim_id=f"claim-summary-{a.id}",
        )
        for a in ranked[1:]
    )
    return DocumentSection(section_id="summary", heading="Professional Summary", items=(item,), omitted=omitted)


def build_experience_section(
    graph: TruthGraph, opp: Opportunity | None, max_bullets_per_role: int
) -> DocumentSection:
    """Experience: one role header per verified `employment.title`, plus
    the founder's actual responsibility/achievement bullets for that role,
    selected and ordered by relevance to the posting's requirements. Dates
    render as "Jan 2026 - Present" (a rendered date carries the employment
    record's own evidence ids, like any other claim). Roles are ordered
    most-recent-first (standard CV convention); this ordering choice is a
    named assumption, see the work order return."""
    role_assertions: dict[str, dict[str, AtomicAssertion]] = {}
    for a in graph.assertions.values():
        if a.verification_status != VerificationStatus.VERIFIED:
            continue
        if not a.predicate.startswith("employment."):
            continue
        field = a.predicate.split(".", 1)[1]
        if field == "responsibility":
            continue  # collected separately below (a collection field)
        role_assertions.setdefault(a.subject_id, {})[field] = a

    responsibility_assertions: dict[str, list[AtomicAssertion]] = {}
    for a in graph.assertions.values():
        if (
            a.predicate == "employment.responsibility"
            and a.verification_status == VerificationStatus.VERIFIED
        ):
            responsibility_assertions.setdefault(a.subject_id, []).append(a)

    # Role membership only -- NOT an admissibility check. The relation's own
    # `verification_status` reflects whether the achievement text
    # independently proves it happened at this specific employer (it rarely
    # does: an achievement sentence like "Reduced pipeline latency by 35%"
    # doesn't name the org), so `_wire_employment_achievement_relation`
    # (`truth/graph.py`, frozen) marks most such relations UNVERIFIED even
    # when the achievement itself is a verified, evidence-backed assertion.
    # Requiring the relation to be VERIFIED here would silently drop nearly
    # every achievement bullet; the achievement's own claim is validated on
    # its own evidence by `validate_artifact_claims` regardless of this
    # relation's status, so any relation of this type is used to determine
    # which role an achievement belongs to.
    achieved_during: dict[str, set[str]] = {}
    for rel in graph.relations.values():
        if rel.relation_type == RelationType.ACHIEVED_DURING:
            achieved_during.setdefault(rel.source_id, set()).add(rel.target_id)

    achievement_assertions: dict[str, AtomicAssertion] = {
        a.subject_id: a
        for a in graph.assertions.values()
        if a.predicate == "achievement.statement" and a.verification_status == VerificationStatus.VERIFIED
    }

    opp_terms = _opportunity_terms(opp)

    def _sort_key(role_id: str) -> tuple:
        fields = role_assertions[role_id]
        start = fields["start_date"].value if "start_date" in fields else None
        end = fields["end_date"].value if "end_date" in fields else None
        # None end_date ("Present") sorts as the most recent.
        end_key = (1,) if end is None else (0, end)
        start_key = start if start is not None else _MIN_DATE
        return (end_key, start_key)

    role_ids = [rid for rid in role_assertions if "title" in role_assertions[rid]]
    role_ids.sort(key=_sort_key, reverse=True)

    items: list[DocumentItem] = []
    omitted: list[OmittedItem] = []

    for role_id in role_ids:
        fields = role_assertions[role_id]
        title_a = fields["title"]
        title = str(title_a.value)
        header_aids = [title_a.id]
        header_eids = list(title_a.evidence_ids)

        header = title
        if "organization" in fields:
            org_a = fields["organization"]
            header += f" | {org_a.value}"
            header_aids.append(org_a.id)
            header_eids.extend(org_a.evidence_ids)

        start_a = fields.get("start_date")
        end_a = fields.get("end_date")
        if start_a is not None:
            start_text = _render_date_value(start_a.value, graph, start_a.evidence_ids)
            if end_a is not None:
                end_text = _render_date_value(end_a.value, graph, end_a.evidence_ids)
            else:
                end_text = _render_present(graph, start_a.evidence_ids)
            header += f" ({start_text} – {end_text})"
            header_aids.append(start_a.id)
            header_eids.extend(start_a.evidence_ids)
            if end_a is not None:
                header_aids.append(end_a.id)
                header_eids.extend(end_a.evidence_ids)

        items.append(DocumentItem(GeneratedClaim(
            claim_id=f"claim-role-{role_id}",
            text=header,
            section_id="experience",
            assertion_ids=tuple(header_aids),
            evidence_ids=tuple(header_eids),
            predicate="employment.record",
            authorized_value=header,
        )))

        bullet_assertions: list[AtomicAssertion] = []
        for ach_id in sorted(achieved_during.get(role_id, ())):
            a = achievement_assertions.get(ach_id)
            if a is not None:
                bullet_assertions.append(a)
        bullet_assertions.extend(responsibility_assertions.get(role_id, ()))

        def _bullet_score(a: AtomicAssertion) -> int:
            return len(_terms(str(a.value)) & opp_terms)

        ordered = sorted(
            enumerate(bullet_assertions),
            key=lambda pair: (-_bullet_score(pair[1]), pair[0]),
        )
        ordered_assertions = [a for _, a in ordered]
        selected = ordered_assertions[:max_bullets_per_role]
        left_out = ordered_assertions[max_bullets_per_role:]

        for a in selected:
            text = str(a.value)
            items.append(DocumentItem(GeneratedClaim(
                claim_id=f"claim-bullet-{a.id}",
                text=text,
                section_id="experience",
                assertion_ids=(a.id,),
                evidence_ids=a.evidence_ids,
                predicate=a.predicate,
                authorized_value=text,
            )))
        for a in left_out:
            omitted.append(OmittedItem(
                section_id="experience",
                text=str(a.value),
                reason="relevance rank / length budget",
                claim_id=f"claim-bullet-{a.id}",
            ))

    return DocumentSection(section_id="experience", heading="Professional Experience", items=tuple(items), omitted=tuple(omitted))


_MIN_DATE = _date.min


def _format_month_year(value) -> str:
    """Render a date as "Jan 2026" (brief-mandated format). `value` is
    whatever `truth.graph` projected for `employment.start_date`/`end_date`
    -- a `datetime.date` for every current pack, but this also accepts an
    already-ISO string defensively."""
    if isinstance(value, _date):
        return value.strftime("%b %Y")
    text = str(value)
    try:
        y, m, d = text.split("-")
        return _date(int(y), int(m), int(d)).strftime("%b %Y")
    except (ValueError, TypeError):
        return text


def _render_date_value(value, graph: TruthGraph, evidence_ids: tuple[str, ...]) -> str:
    """Render a date for a claim: prefer the brief-mandated "Jan 2026" form,
    but only when the month name it introduces is textually present in the
    record's own cited evidence (guard 9, `truth/validator.py`, requires
    every material word in a claim to be covered by its evidence); otherwise
    fall back to the ISO form the evidence itself uses, which is always
    covered by construction. On both shipped synthetic packs today, every
    date's evidence stores the date as an ISO string (e.g.
    "2023-01-01 to 2026-08-31") with no English month name in it, so this
    always falls back to ISO on the current fixtures -- see the work order
    return; this is a genuine, reported deviation from the brief's exact
    display string, not a rendering bug."""
    evidence_text = " ".join(
        (graph.evidence_records[eid].content or "")
        for eid in evidence_ids
        if eid in graph.evidence_records and graph.evidence_records[eid].content
    )
    preferred = _format_month_year(value)
    month_word = preferred.split(" ", 1)[0]
    if month_word.casefold() in evidence_text.casefold():
        return preferred
    return value.isoformat() if isinstance(value, _date) else str(value)


def _render_present(graph: TruthGraph, evidence_ids: tuple[str, ...]) -> str:
    """"Present" is not in `truth/connective_terms.txt` (frozen) or the
    validator's non-material-word set, so it can only be rendered for a
    still-open role when the record's own evidence literally uses that
    word; otherwise this renders nothing rather than invent an unevidenced
    word (no role in either shipped synthetic pack is actually open-ended,
    so this path is untested by fixture data -- see the work order
    return)."""
    evidence_text = " ".join(
        (graph.evidence_records[eid].content or "")
        for eid in evidence_ids
        if eid in graph.evidence_records and graph.evidence_records[eid].content
    )
    if "present" in evidence_text.casefold():
        return "Present"
    return ""


def build_skills_section(
    graph: TruthGraph, opp: Opportunity | None, max_skills: int
) -> DocumentSection:
    """Skills grouped by the pack's own `skill.category` (BRIEF-FR-006 D1F;
    `truth/models.py::SkillRecord.category`, optional), ordered by relevance,
    with proficiency shown honestly. Selection and ranking are unchanged from
    D1: the most opportunity-relevant skills are chosen first, up to
    `max_skills`. Grouping is then applied to the selected set only --
    same-category items are made contiguous, with each category's position
    driven by the best (most relevant) rank of any skill inside it, so the
    most relevant category still leads. If no selected skill carries a
    category (a pack that never sets the field), this falls back to the
    plain relevance order with no reordering."""
    name_assertions = [
        a for a in graph.assertions.values()
        if a.predicate == "skill.name" and a.verification_status == VerificationStatus.VERIFIED
    ]
    proficiency_by_subject = {
        a.subject_id: a
        for a in graph.assertions.values()
        if a.predicate == "skill.proficiency" and a.verification_status == VerificationStatus.VERIFIED
    }
    category_by_subject = {
        a.subject_id: a
        for a in graph.assertions.values()
        if a.predicate == "skill.category" and a.verification_status == VerificationStatus.VERIFIED
    }

    opp_terms = {s.casefold() for s in (opp.skills if opp is not None else ())}

    def _relevant(a: AtomicAssertion) -> bool:
        return str(a.value).casefold() in opp_terms

    ranked = sorted(name_assertions, key=lambda a: (0 if _relevant(a) else 1, a.id))
    selected = ranked[:max_skills]
    left_out = ranked[max_skills:]

    has_categories = any(a.subject_id in category_by_subject for a in selected)
    if has_categories:
        relevance_rank = {a.id: idx for idx, a in enumerate(selected)}
        groups: dict[str, list[AtomicAssertion]] = {}
        for a in selected:
            cat = category_by_subject.get(a.subject_id)
            groups.setdefault(str(cat.value) if cat is not None else "General", []).append(a)
        group_order = sorted(
            groups.keys(), key=lambda cat: min(relevance_rank[a.id] for a in groups[cat])
        )
        grouped_selected = [
            a
            for cat in group_order
            for a in sorted(groups[cat], key=lambda a: relevance_rank[a.id])
        ]
    else:
        grouped_selected = selected

    items: list[DocumentItem] = []
    for a in grouped_selected:
        prof = proficiency_by_subject.get(a.subject_id)
        cat = category_by_subject.get(a.subject_id)
        # `authorized_value` stays the bare skill name -- the exact value the
        # cited `skill.name` assertion actually authorizes -- never the
        # decorated display `text` below. This was already true (`prof` was
        # always `None` on every shipped fixture, so it was untested); fixing
        # it here as part of the D1F Skills-grouping change is what surfaced
        # it against a pack that now sets proficiency/category for real.
        authorized_value = str(a.value)
        text = authorized_value
        aids = [a.id]
        eids = list(a.evidence_ids)
        if prof is not None:
            text = f"{text} ({prof.value})"
            aids.append(prof.id)
            eids.extend(prof.evidence_ids)
        if cat is not None:
            text = f"{text} [{cat.value}]"
            aids.append(cat.id)
            eids.extend(cat.evidence_ids)
        items.append(DocumentItem(GeneratedClaim(
            claim_id=f"claim-skill-{a.id}",
            text=text,
            section_id="skills",
            assertion_ids=tuple(aids),
            evidence_ids=tuple(eids),
            predicate="skill.name",
            authorized_value=authorized_value,
        )))

    omitted = tuple(
        OmittedItem(
            section_id="skills",
            text=str(a.value),
            reason="length budget: only the most relevant skills are shown",
            claim_id=f"claim-skill-{a.id}",
        )
        for a in left_out
    )

    return DocumentSection(section_id="skills", heading="Technical Skills & Competencies", items=tuple(items), omitted=omitted)


def build_education_section(graph: TruthGraph) -> DocumentSection:
    fields_by_subject: dict[str, dict[str, AtomicAssertion]] = {}
    for a in graph.assertions.values():
        if a.verification_status != VerificationStatus.VERIFIED or not a.predicate.startswith("education."):
            continue
        fields_by_subject.setdefault(a.subject_id, {})[a.predicate.split(".", 1)[1]] = a

    items: list[DocumentItem] = []
    for subject_id in sorted(fields_by_subject):
        fields = fields_by_subject[subject_id]
        if "qualification" not in fields or "institution" not in fields:
            continue
        qualification_a = fields["qualification"]
        institution_a = fields["institution"]
        text = f"{qualification_a.value} | {institution_a.value}"
        aids = [qualification_a.id, institution_a.id]
        eids = list(qualification_a.evidence_ids) + list(institution_a.evidence_ids)
        start_a = fields.get("start_date")
        end_a = fields.get("end_date")
        if start_a is not None and end_a is not None:
            start_text = _render_date_value(start_a.value, graph, start_a.evidence_ids)
            end_text = _render_date_value(end_a.value, graph, end_a.evidence_ids)
            text += f" ({start_text} – {end_text})"
            aids.extend([start_a.id, end_a.id])
            eids.extend(start_a.evidence_ids)
            eids.extend(end_a.evidence_ids)
        items.append(DocumentItem(GeneratedClaim(
            claim_id=f"claim-education-{subject_id}",
            text=text,
            section_id="education",
            assertion_ids=tuple(aids),
            evidence_ids=tuple(eids),
            predicate="education.record",
            authorized_value=text,
        )))

    return DocumentSection(section_id="education", heading="Education", items=tuple(items))


def build_certifications_section(graph: TruthGraph) -> DocumentSection:
    fields_by_subject: dict[str, dict[str, AtomicAssertion]] = {}
    for a in graph.assertions.values():
        if a.verification_status != VerificationStatus.VERIFIED or not a.predicate.startswith("certification."):
            continue
        fields_by_subject.setdefault(a.subject_id, {})[a.predicate.split(".", 1)[1]] = a

    items: list[DocumentItem] = []
    omitted: list[OmittedItem] = []
    for subject_id in sorted(fields_by_subject):
        fields = fields_by_subject[subject_id]
        if "name" not in fields or "issuer" not in fields:
            continue
        name_a = fields["name"]
        issuer_a = fields["issuer"]
        state_a = fields.get("state")

        if (
            state_a is not None
            and str(state_a.value) == "planned"
            and _HELD_WORD_RE.search(str(name_a.value))
        ):
            # The credential's own name contains a "held" word (e.g.
            # "Certified Group Analytics Architect"): no framing of a claim
            # naming it can satisfy `_planned_credential_reasons` (frozen),
            # which rejects any claim containing a held-word when the
            # certification is planned. Omit rather than misrepresent it as
            # held or fabricate wording the validator will not accept.
            omitted.append(OmittedItem(
                section_id="certifications",
                text=str(name_a.value),
                reason=(
                    "planned certification's own name contains a 'held' word "
                    "(e.g. 'Certified'); no honest rendering satisfies the "
                    "validator's planned-credential guard -- see the work "
                    "order return"
                ),
                claim_id=f"claim-certification-{subject_id}",
            ))
            continue

        if state_a is not None and str(state_a.value) == "planned":
            # `ClaimValidator._planned_credential_reasons` (frozen) rejects
            # ANY claim naming a planned certification unless the claim
            # itself contains a "planning" word (e.g. "planning", "pursue")
            # and no "held" word (e.g. "certified", "completed") --
            # otherwise it reads as the founder claiming to already hold it.
            # Rather than compose new planning language of our own (which
            # would also have to separately satisfy guard 9's evidence-
            # coverage check), quote the record's own evidence verbatim: the
            # pack's evidence for a planned certification is already written
            # as "Planning to pursue the {name} certification from
            # {issuer}." -- an approved fact, not synthesized prose.
            evidence_text = next(
                (
                    graph.evidence_records[eid].content
                    for eid in name_a.evidence_ids
                    if eid in graph.evidence_records and graph.evidence_records[eid].content
                ),
                None,
            )
            if evidence_text:
                text = evidence_text
                aids = [name_a.id, issuer_a.id, state_a.id]
                eids = list(dict.fromkeys(list(name_a.evidence_ids) + list(issuer_a.evidence_ids) + list(state_a.evidence_ids)))
                items.append(DocumentItem(GeneratedClaim(
                    claim_id=f"claim-certification-{subject_id}",
                    text=text,
                    section_id="certifications",
                    assertion_ids=tuple(aids),
                    evidence_ids=tuple(eids),
                    predicate="certification.record",
                    authorized_value=text,
                )))
                continue

        text = f"{name_a.value} | {issuer_a.value}"
        aids = [name_a.id, issuer_a.id]
        eids = list(name_a.evidence_ids) + list(issuer_a.evidence_ids)
        issued_a = fields.get("issued_date")
        if issued_a is not None:
            text += f" ({_render_date_value(issued_a.value, graph, issued_a.evidence_ids)})"
            aids.append(issued_a.id)
            eids.extend(issued_a.evidence_ids)
        items.append(DocumentItem(GeneratedClaim(
            claim_id=f"claim-certification-{subject_id}",
            text=text,
            section_id="certifications",
            assertion_ids=tuple(aids),
            evidence_ids=tuple(eids),
            predicate="certification.record",
            authorized_value=text,
        )))

    return DocumentSection(section_id="certifications", heading="Certifications", items=tuple(items), omitted=tuple(omitted))


def build_projects_section(graph: TruthGraph) -> DocumentSection:
    """Projects: the pack's portfolio items, with URLs when the pack states
    one. Neither shipped synthetic pack currently sets `PortfolioItem.url`
    (see the work order return for this content-threshold gap), so the URL
    clause is written and available but not exercised by either fixture."""
    fields_by_subject: dict[str, dict[str, AtomicAssertion]] = {}
    for a in graph.assertions.values():
        if a.verification_status != VerificationStatus.VERIFIED or not a.predicate.startswith("portfolio."):
            continue
        fields_by_subject.setdefault(a.subject_id, {})[a.predicate.split(".", 1)[1]] = a

    items: list[DocumentItem] = []
    for subject_id in sorted(fields_by_subject):
        fields = fields_by_subject[subject_id]
        if "title" not in fields or "summary" not in fields:
            continue
        title_a = fields["title"]
        summary_a = fields["summary"]
        text = f"{title_a.value} — {summary_a.value}"
        aids = [title_a.id, summary_a.id]
        eids = list(title_a.evidence_ids) + list(summary_a.evidence_ids)
        url_a = fields.get("url")
        if url_a is not None:
            text += f" ({url_a.value})"
            aids.append(url_a.id)
            eids.extend(url_a.evidence_ids)
        items.append(DocumentItem(GeneratedClaim(
            claim_id=f"claim-project-{subject_id}",
            text=text,
            section_id="projects",
            assertion_ids=tuple(aids),
            evidence_ids=tuple(eids),
            predicate="portfolio.record",
            authorized_value=text,
        )))

    return DocumentSection(section_id="projects", heading="Projects", items=tuple(items))


def build_languages_section(graph: TruthGraph) -> DocumentSection:
    fields_by_subject: dict[str, dict[str, AtomicAssertion]] = {}
    for a in graph.assertions.values():
        if a.verification_status != VerificationStatus.VERIFIED or not a.predicate.startswith("language."):
            continue
        fields_by_subject.setdefault(a.subject_id, {})[a.predicate.split(".", 1)[1]] = a

    items: list[DocumentItem] = []
    for subject_id in sorted(fields_by_subject):
        fields = fields_by_subject[subject_id]
        if "language" not in fields or "proficiency" not in fields:
            continue
        lang_a = fields["language"]
        prof_a = fields["proficiency"]
        text = f"{lang_a.value} — {prof_a.value}"
        items.append(DocumentItem(GeneratedClaim(
            claim_id=f"claim-language-{subject_id}",
            text=text,
            section_id="languages",
            assertion_ids=(lang_a.id, prof_a.id),
            evidence_ids=tuple(list(lang_a.evidence_ids) + list(prof_a.evidence_ids)),
            predicate="language.record",
            authorized_value=text,
        )))

    return DocumentSection(section_id="languages", heading="Languages", items=tuple(items))


def build_achievements_section(graph: TruthGraph) -> DocumentSection:
    """Verified quantified achievements from `MetricAssertion`s (kept from
    the pre-existing compiler: BRIEF-FR-005 D1's period-terminated-context
    fix is preserved verbatim)."""
    metric_assertions = [
        m for m in graph.metrics.values() if m.verification_status == VerificationStatus.VERIFIED
    ]
    items: list[DocumentItem] = []
    for m in metric_assertions:
        unit_str = f" {m.unit}" if m.unit and m.unit not in ("count", "number") else ""
        metric_context = m.context.rstrip(".")
        text = f"{metric_context}: {m.numeric_value}{unit_str}"
        items.append(DocumentItem(GeneratedClaim(
            claim_id=f"claim-metric-{m.id}",
            text=text,
            section_id="achievements",
            assertion_ids=(m.id,),
            evidence_ids=m.evidence_ids,
            predicate="metric",
            authorized_value=text,
        )))
    return DocumentSection(section_id="achievements", heading="Selected Quantified Achievements", items=tuple(items))
