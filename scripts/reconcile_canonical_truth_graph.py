from __future__ import annotations

import argparse
import base64
from calendar import monthrange
from copy import deepcopy
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import re
import textwrap
from typing import Any

import yaml

from truth.ingest import load_document
from truth.pack import _graph_to_canonical_dict, compute_truth_pack_hash


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.casefold())).strip("-")


def _evidence(
    evidence_id: str,
    source: str,
    locator: str,
    content: str,
    *,
    approximate: bool = False,
) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "content": content,
        "source": source,
        "locator": locator,
        "assertion_type": "direct_fact",
        "verification_status": "approximate" if approximate else "verified",
    }


def _source_content(value: Any, additions: dict[str, Any] | None = None) -> str:
    document = {"source_record": value}
    if additions:
        document["explicit_normalizations"] = additions
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _month_date(value: Any, *, end: bool = False) -> tuple[str | None, bool]:
    if value is None or value == "":
        return None, False
    raw = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw, False
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        year, month = map(int, raw.split("-"))
        if not 1 <= month <= 12:
            raise ValueError(f"invalid month in canonical source date: {raw}")
        normalized = date(year, month, monthrange(year, month)[1] if end else 1)
        return normalized.isoformat(), True
    if re.fullmatch(r"\d{4}", raw):
        # Keep year-only facts in an assertion; do not invent a month or day.
        return None, False
    raise ValueError(f"unsupported canonical source date precision: {raw}")


def _skills_and_tools(
    markdown: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, tuple[str, str, str]]]:
    evidence_documents: dict[str, tuple[str, str, str]] = {}
    skills: list[dict[str, Any]] = []
    in_skill_table = False
    for line in markdown.splitlines():
        if line.strip() == "## Skills / Capabilities":
            in_skill_table = True
            continue
        if in_skill_table and line.startswith("## "):
            in_skill_table = False
        if not in_skill_table or not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 3 or cells[0].casefold() == "family" or set(cells[0]) <= {"-", ":"}:
            continue
        family, phrases, provenance = cells
        evidence_id = f"cv9-skill-evidence-{_slug(family)}"
        evidence_documents[evidence_id] = (
            f"founder/Supporting_Documents/MASTER_SKILLS_AND_TECH_STACK.md",
            f"Skills / Capabilities/{family}",
            line.strip(),
        )
        for index, phrase in enumerate(item.strip() for item in phrases.split(",") if item.strip()):
            skills.append({
                "id": f"skill-{_slug(family)}-{index + 1}",
                "name": phrase,
                "evidence_ids": [evidence_id],
                "category": family,
            })

    tools: list[dict[str, Any]] = []
    section = False
    category: str | None = None
    category_lines: dict[str, str] = {}
    for line in markdown.splitlines():
        if line.strip() == "## Technology Inventory by Category":
            section = True
            continue
        if section and line.startswith("## "):
            break
        if not section:
            continue
        if line.startswith("### "):
            category = line[4:].strip()
            continue
        if not category or not line.strip() or line.lstrip().startswith("|"):
            continue
        evidence_id = f"cv9-tool-evidence-{_slug(category)}"
        category_lines.setdefault(category, line.strip())
        for index, technology in enumerate(item.strip().rstrip(".") for item in line.split(";") if item.strip()):
            tools.append({
                "id": f"tool-{_slug(category)}-{index + 1}",
                "name": technology,
                "evidence_ids": [evidence_id],
                "category": category,
            })

    for category, content in category_lines.items():
        evidence_id = f"cv9-tool-evidence-{_slug(category)}"
        evidence_documents[evidence_id] = (
            "founder/Supporting_Documents/MASTER_SKILLS_AND_TECH_STACK.md",
            f"Technology Inventory by Category/{category}",
            f"{category}: {content}",
        )
    return skills, tools, evidence_documents


def reconcile_document(
    base_document: dict[str, Any],
    source_pack: dict[str, Any],
    skills_markdown: str,
    cv_manifest: dict[str, Any],
) -> dict[str, Any]:
    if source_pack.get("cv_system", {}).get("canonical_cv_count") != 9:
        raise ValueError("canonical source pack is not the approved nine-CV version")
    if "variants" not in cv_manifest or len(cv_manifest["variants"]) != 9:
        raise ValueError("repository CV manifest is not the canonical nine-variant manifest")
    for key in ("identity", "employment", "education", "certifications", "projects"):
        if key not in source_pack:
            raise ValueError(f"canonical source pack is missing {key}")

    result = deepcopy(base_document)
    evidence: list[dict[str, Any]] = result.setdefault("evidence", [])
    existing_ids = {item["id"] for item in evidence}

    def add(item: dict[str, Any]) -> str:
        if item["id"] in existing_ids:
            raise ValueError(f"duplicate generated canonical evidence id: {item['id']}")
        evidence.append(item)
        existing_ids.add(item["id"])
        return item["id"]

    identity = source_pack["identity"]
    location_parts = [part.strip() for part in str(identity.get("location", "")).split(",", 1)]
    identity_fields: dict[str, Any] = {"name": identity["name"]}
    for source_key, target_key in (
        ("email", "email"), ("phone", "phone"), ("website", "website"),
        ("linkedin", "linkedin"), ("github", "github"),
    ):
        if identity.get(source_key):
            identity_fields[target_key] = identity[source_key]
    if location_parts and location_parts[0]:
        identity_fields["location_city"] = location_parts[0]
    if len(location_parts) == 2 and location_parts[1]:
        identity_fields["location_country"] = location_parts[1]
    identity_evidence_ids = []
    identity_field_evidence: dict[str, str] = {}
    for field_name, field_value in identity_fields.items():
        evidence_id = add(_evidence(
            f"cv9-identity-{_slug(field_name)}-evidence",
            "founder/Supporting_Documents/truth_pack.yaml",
            f"identity.{field_name}",
            f"{field_name}: {field_value}",
        ))
        identity_evidence_ids.append(evidence_id)
        identity_field_evidence[field_name] = evidence_id
    identity_evidence_id = add(_evidence(
        "cv9-identity-source",
        "founder/Supporting_Documents/truth_pack.yaml",
        "identity",
        _source_content(identity),
    ))
    identity_evidence_ids.append(identity_evidence_id)
    for source_key in ("citizenship", "remote_work"):
        if source_key in identity:
            identity_field_evidence[source_key] = add(_evidence(
                f"cv9-identity-{source_key}-evidence",
                "founder/Supporting_Documents/truth_pack.yaml",
                f"identity.{source_key}",
                f"{source_key}: {str(identity[source_key]).lower()}",
            ))
    identity_record: dict[str, Any] = {
        "name": identity["name"],
        "evidence_ids": identity_evidence_ids,
    }
    for key in ("email", "phone", "website", "linkedin", "github", "location_city", "location_country"):
        if key in identity_fields:
            identity_record[key] = identity_fields[key]
    result["identity"] = identity_record

    assertions = [
        item for item in result.get("assertions", [])
        if not (item.get("subject_id") == "identity" and item.get("predicate") in {"identity.citizenship", "identity.remote_work_available"})
    ]
    if identity.get("citizenship"):
        assertions.append({
            "id": "cv9-identity-citizenship",
            "subject_id": "identity",
            "predicate": "identity.citizenship",
            "value": identity["citizenship"],
            "evidence_ids": [identity_field_evidence["citizenship"]],
            "assertion_type": "direct_fact",
            "verification_status": "verified",
        })
    if "remote_work" in identity:
        assertions.append({
            "id": "cv9-identity-remote-work",
            "subject_id": "identity",
            "predicate": "identity.remote_work_available",
            "value": str(bool(identity["remote_work"])).lower(),
            "evidence_ids": [identity_field_evidence["remote_work"]],
            "assertion_type": "direct_fact",
            "verification_status": "verified",
        })
    result["assertions"] = assertions

    career = result["career_profile"]
    career_evidence_ids = set(career.get("evidence_ids", []))
    career_evidence_ids.add(identity_evidence_id)
    employment_records: list[dict[str, Any]] = []
    year_assertions: list[dict[str, Any]] = []
    for index, record in enumerate(source_pack["employment"], start=1):
        start_date, start_approximate = _month_date(record.get("start"))
        end_date, end_approximate = _month_date(record.get("end"), end=True)
        normalized_dates = {"start_date": start_date, "end_date": end_date}
        evidence_id = add(_evidence(
            f"cv9-employment-evidence-{index:02d}",
            "founder/Supporting_Documents/truth_pack.yaml",
            f"employment[{index - 1}]",
            _source_content(record, normalized_dates),
            approximate=start_approximate or end_approximate,
        ))
        organization_evidence_id = add(_evidence(
            f"cv9-employment-organization-evidence-{index:02d}",
            "founder/Supporting_Documents/truth_pack.yaml",
            f"employment[{index - 1}].organization",
            str(record["organization"]),
        ))
        title_evidence_id = add(_evidence(
            f"cv9-employment-title-evidence-{index:02d}",
            "founder/Supporting_Documents/truth_pack.yaml",
            f"employment[{index - 1}].title",
            str(record["title"]),
        ))
        career_evidence_ids.update({evidence_id, organization_evidence_id, title_evidence_id})
        emp_id = f"employment-{index:02d}-{_slug(record['organization'])}-{_slug(record['title'])}"
        employment_records.append({
            "id": emp_id,
            "organization": record["organization"],
            "title": record["title"],
            "start_date": start_date,
            "end_date": end_date,
            "evidence_ids": [evidence_id, organization_evidence_id, title_evidence_id],
            "responsibilities": list(record.get("summary", [])),
            "achievements": [],
        })
        if record.get("end") and re.fullmatch(r"\d{4}", str(record["end"])):
            year_evidence = add(_evidence(
                f"cv9-employment-end-year-evidence-{index:02d}",
                "founder/Supporting_Documents/truth_pack.yaml",
                f"employment[{index - 1}].end",
                f"End year: {record['end']}",
            ))
            career_evidence_ids.add(year_evidence)
            year_assertions.append({
                "id": f"cv9-employment-end-year-{index:02d}",
                "subject_id": emp_id,
                "predicate": "employment.end_year",
                "value": str(record["end"]),
                "evidence_ids": [year_evidence],
                "assertion_type": "direct_fact",
                "verification_status": "verified",
            })
    career["employment"] = employment_records

    education_records: list[dict[str, Any]] = []
    for index, record in enumerate(source_pack["education"], start=1):
        start_date, start_approximate = _month_date(record.get("start"))
        end_date, end_approximate = _month_date(record.get("end"), end=True)
        evidence_id = add(_evidence(
            f"cv9-education-evidence-{index:02d}",
            "founder/Supporting_Documents/truth_pack.yaml",
            f"education[{index - 1}]",
            _source_content(record, {"start_date": start_date, "end_date": end_date}),
            approximate=start_approximate or end_approximate,
        ))
        career_evidence_ids.add(evidence_id)
        edu_id = f"education-{index:02d}-{_slug(record['institution'])}"
        item: dict[str, Any] = {
            "id": edu_id,
            "institution": record["institution"],
            "qualification": record["qualification"],
            "evidence_ids": [evidence_id],
        }
        if start_date:
            item["start_date"] = start_date
        if end_date:
            item["end_date"] = end_date
        education_records.append(item)
        for field in ("start", "end"):
            raw_date = record.get(field)
            if raw_date and re.fullmatch(r"\d{4}", str(raw_date)):
                year_evidence = add(_evidence(
                    f"cv9-education-{field}-year-evidence-{index:02d}",
                    "founder/Supporting_Documents/truth_pack.yaml",
                    f"education[{index - 1}].{field}",
                    f"{field.title()} year: {raw_date}",
                ))
                career_evidence_ids.add(year_evidence)
                year_assertions.append({
                    "id": f"cv9-education-{field}-year-{index:02d}",
                    "subject_id": edu_id,
                    "predicate": f"education.{field}_year",
                    "value": str(raw_date),
                    "evidence_ids": [year_evidence],
                    "assertion_type": "direct_fact",
                    "verification_status": "verified",
                })
    career["education"] = education_records

    certifications: list[dict[str, Any]] = []
    for index, record in enumerate(source_pack["certifications"], start=1):
        evidence_id = add(_evidence(
            f"cv9-certification-evidence-{index:02d}",
            "founder/Supporting_Documents/truth_pack.yaml",
            f"certifications[{index - 1}]",
            _source_content(record),
        ))
        career_evidence_ids.add(evidence_id)
        name_evidence_id = add(_evidence(
            f"cv9-certification-name-evidence-{index:02d}",
            "founder/Supporting_Documents/truth_pack.yaml",
            f"certifications[{index - 1}].name",
            str(record["name"]),
        ))
        issuer_evidence_id = add(_evidence(
            f"cv9-certification-issuer-evidence-{index:02d}",
            "founder/Supporting_Documents/truth_pack.yaml",
            f"certifications[{index - 1}].issuer",
            str(record["issuer"]),
        ))
        career_evidence_ids.update({name_evidence_id, issuer_evidence_id})
        state_evidence_id = add(_evidence(
            f"cv9-certification-state-evidence-{index:02d}",
            "founder/Supporting_Documents/truth_pack.yaml",
            f"certifications[{index - 1}].state",
            "Completed state normalized from the canonical completed-certification collection; source has no separate state field.",
            approximate=True,
        ))
        career_evidence_ids.add(state_evidence_id)
        cert_id = f"certification-{index:02d}-{_slug(record['name'])}"
        certifications.append({
            "id": cert_id,
            "name": record["name"],
            "issuer": record["issuer"],
            "state": "completed",
            "evidence_ids": [evidence_id, name_evidence_id, issuer_evidence_id, state_evidence_id],
        })
        if record.get("year") is not None:
            year_evidence = add(_evidence(
                f"cv9-certification-year-evidence-{index:02d}",
                "founder/Supporting_Documents/truth_pack.yaml",
                f"certifications[{index - 1}].year",
                f"Certification year: {record['year']}",
            ))
            career_evidence_ids.add(year_evidence)
            year_assertions.append({
                "id": f"cv9-certification-year-{index:02d}",
                "subject_id": cert_id,
                "predicate": "certification.year",
                "value": str(record["year"]),
                "evidence_ids": [year_evidence],
                "assertion_type": "direct_fact",
                "verification_status": "verified",
            })
    career["certifications"] = certifications

    skill_records, tool_records, skill_and_tool_evidence = _skills_and_tools(skills_markdown)
    skill_evidence_ids = sorted({evidence_id for item in skill_records for evidence_id in item["evidence_ids"]})
    tool_evidence_ids = sorted({evidence_id for item in tool_records for evidence_id in item["evidence_ids"]})
    for evidence_id, (source, locator, content) in skill_and_tool_evidence.items():
        add(_evidence(evidence_id, source, locator, content))
    career["skills"] = skill_records
    career["languages"] = []
    for index, language in enumerate(identity.get("languages", []), start=1):
        if " - " not in language:
            raise ValueError("canonical language entries must include explicit proficiency")
        language_name, proficiency = language.rsplit(" - ", 1)
        career["languages"].append({
            "id": f"language-{index:02d}-{_slug(language_name)}",
            "language": language_name,
            "proficiency": proficiency,
            "evidence_ids": [identity_evidence_id],
        })
    career["evidence_ids"] = sorted(career_evidence_ids | set(skill_evidence_ids) | {identity_evidence_id})

    capability = result["capability_profile"]
    capability_evidence_ids = set(capability.get("evidence_ids", [])) | set(tool_evidence_ids)
    portfolio: list[dict[str, Any]] = []
    for project_id, project in source_pack["projects"].items():
        evidence_id = f"cv9-project-evidence-{_slug(project_id)}"
        add(_evidence(
            evidence_id,
            "founder/Supporting_Documents/truth_pack.yaml",
            f"projects/{project_id}",
            _source_content(project),
        ))
        capability_evidence_ids.add(evidence_id)
        links = project.get("links", [])
        project_url = next((link for link in links if isinstance(link, str) and link.startswith(("https://", "http://"))), None)
        portfolio.append({
            "id": f"portfolio-{_slug(project_id)}",
            "title": project["title"],
            "summary": "\n".join(project.get("bullets", [])),
            "evidence_ids": [evidence_id],
            "metric_verification": "unavailable",
            **({"url": project_url} if project_url else {}),
        })
    capability["portfolio"] = portfolio
    capability["tools"] = tool_records
    capability["evidence_ids"] = sorted(capability_evidence_ids)
    result["assertions"].extend(year_assertions)
    return result


def _decode_pack(path: Path) -> tuple[dict[str, Any], bytes]:
    compressed = base64.b64decode(b"".join(path.read_bytes().split()), validate=True)
    raw = gzip.decompress(compressed)
    document = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("runtime truth pack must be a mapping")
    return document, raw


def build(
    *,
    source_root: Path,
    repo_root: Path,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    repo_root = repo_root.resolve()
    source_dir = source_root / "Supporting_Documents"
    source_pack = yaml.safe_load((source_dir / "truth_pack.yaml").read_text(encoding="utf-8"))
    skills_markdown = (source_dir / "MASTER_SKILLS_AND_TECH_STACK.md").read_text(encoding="utf-8")
    cv_manifest = yaml.safe_load((repo_root / "founder" / "cv_portfolio.yaml").read_text(encoding="utf-8"))
    base, _ = _decode_pack(repo_root / "founder" / "truth_pack.yaml.gz.b64")
    reconciled = reconcile_document(base, source_pack, skills_markdown, cv_manifest)
    class QuotedSafeDumper(yaml.SafeDumper):
        def represent_str(self, value: str) -> yaml.Node:
            return self.represent_scalar("tag:yaml.org,2002:str", value, style='"')

    QuotedSafeDumper.add_representer(str, QuotedSafeDumper.represent_str)
    raw_text = yaml.dump(reconciled, Dumper=QuotedSafeDumper, sort_keys=False, allow_unicode=True, width=1_000_000)
    graph = load_document(raw_text, "yaml")
    canonical = _graph_to_canonical_dict(graph)
    return {
        "raw": raw_text.encode("utf-8"),
        "graph_hash": compute_truth_pack_hash(graph),
        "counts": {
            "employment": len(reconciled["career_profile"]["employment"]),
            "education": len(reconciled["career_profile"]["education"]),
            "certifications": len(reconciled["career_profile"]["certifications"]),
            "skills": len(reconciled["career_profile"]["skills"]),
            "tools": len(reconciled["capability_profile"]["tools"]),
            "portfolio": len(reconciled["capability_profile"]["portfolio"]),
            "cv_variants": len(cv_manifest["variants"]),
            "evidence": len(reconciled["evidence"]),
            "explicit_metrics": len(canonical.get("metrics", [])),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile the canonical 9-CV source into the runtime truth graph.")
    parser.add_argument("--source-root", required=True, type=Path, help="Folder containing Supporting_Documents and CVs")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = build(source_root=args.source_root, repo_root=args.repo_root)
    raw: bytes = result["raw"]
    encoded = base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode("ascii")
    artifact = args.repo_root / "founder" / "truth_pack.yaml.gz.b64"
    artifact.write_text("\n".join(textwrap.wrap(encoded, 76)) + "\n", encoding="ascii")
    print(json.dumps({
        "status": "RECONCILED",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "graph_sha256": result["graph_hash"],
        "counts": result["counts"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
