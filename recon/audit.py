"""Create a deterministic, local-only adjudication set from a completed run."""
from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path

from recon.classification import classify
from recon.geography import extract
from recon.models import Record


def build_audit_item(record: Record) -> tuple[str, dict]:
    extracted = extract(record)
    decision = classify(record)
    item = {
        "source": record.source, "track": record.track, "title": record.title,
        "record_id": hashlib.sha256(f"{record.source}\0{record.url}\0{record.title}".encode()).hexdigest()[:16],
        "url": record.url,
        "location_text": record.location_text, "raw_text": record.description,
        "raw_payload_pointer": record.raw_payload_pointer,
        "geo_allow": list(extracted.geo_allow), "geo_deny": list(extracted.geo_deny),
        "derived_country": "EG", "derived_verdict": decision.eligibility,
        "derived_reason": decision.eligibility_reason, "adjudication": "pending_raw_text_review",
    }
    return decision.eligibility, item


def main() -> None:
    out_dir = Path("out")
    rows = list(csv.DictReader((out_dir / "opportunities.csv").open(encoding="utf-8")))
    buckets: dict[str, list[dict[str, str]]] = {"eligible": [], "excluded": [], "unclear": []}
    for row in rows:
        record = Record(row["source"], row["track"], row["title"], row["organization"], row["location_text"], row["url"], row["posted_date"], row["description"], row["raw_payload_pointer"])
        eligibility, item = build_audit_item(record)
        buckets[eligibility].append(item)
    rng = random.Random(104)
    sample = {name: rng.sample(items, min(30, len(items))) for name, items in buckets.items()}
    (out_dir / "audit-001.json").write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(", ".join(f"{name}={len(items)}" for name, items in sample.items()))


if __name__ == "__main__":
    main()
