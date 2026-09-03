"""Claim A-16 (BRIEF-FR-006 E23): zero adapters bound to a `manual_only` or `disabled`
source, and zero `prepare`/`submit` automation permissions anywhere in the committed
policy files. An adapter that reads a `manual_only` or `disabled` source is a hard stop."""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from opportunity.adapters import get_all_standard_adapters
from opportunity.registry import SourceRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "docs" / "SOURCE_REGISTRY.yaml"
PERMISSIONS_PATH = REPO_ROOT / "docs" / "AGENT_PERMISSIONS.yaml"


class SourcePolicyBindingTests(unittest.TestCase):
    """A-16: no bound adapter reads a manual_only/disabled source; no prepare/submit permission exists."""

    def test_every_bound_adapter_source_is_read_allowed(self):
        registry = SourceRegistry(REGISTRY_PATH)
        adapters = get_all_standard_adapters()
        self.assertTrue(adapters, "at least one adapter must be bound")
        offenders = []
        for adapter in adapters:
            if not registry.is_read_allowed(adapter.source_id):
                offenders.append(adapter.source_id)
        self.assertEqual([], offenders, f"adapters bound to non-read-allowed sources: {offenders}")

    def test_no_bound_adapter_targets_a_manual_only_or_disabled_registry_entry(self):
        data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
        manual_or_disabled = {
            entry["source_id"]
            for entry in data.get("sources", [])
            if entry.get("policy_status") == "manual_only"
            or entry.get("automation", {}).get("read") == "disabled"
        }
        bound_ids = {adapter.source_id for adapter in get_all_standard_adapters()}
        overlap = bound_ids & manual_or_disabled
        self.assertEqual(set(), overlap, f"bound adapters must never target manual_only/disabled sources: {overlap}")

    def test_zero_prepare_or_submit_permissions_in_source_registry(self):
        data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
        offenders = []
        for entry in data.get("sources", []):
            automation = entry.get("automation", {})
            if automation.get("prepare") not in (None, "disabled"):
                offenders.append((entry["source_id"], "prepare", automation.get("prepare")))
            if automation.get("submit") not in (None, "disabled"):
                offenders.append((entry["source_id"], "submit", automation.get("submit")))
        self.assertEqual([], offenders, f"non-disabled prepare/submit found: {offenders}")

    def test_zero_prepare_or_submit_permissions_in_agent_permissions(self):
        data = yaml.safe_load(PERMISSIONS_PATH.read_text(encoding="utf-8"))
        classes = data.get("action_classes", {})
        for class_id in ("class_2_prepare_external_action", "class_3_controlled_external_action",
                         "class_4_legal_or_commercial_commitment"):
            with self.subTest(action_class=class_id):
                self.assertFalse(classes.get(class_id, {}).get("enabled", False), f"{class_id} must stay disabled")
        for permission in data.get("adapter_permissions", []):
            with self.subTest(host=permission.get("host")):
                self.assertEqual(
                    "READ_ONLY_QUERY", permission.get("classification"),
                    "no adapter_permissions entry may carry a prepare/submit classification",
                )

    def test_every_e23_added_or_corrected_entry_has_policy_status_and_dated_review(self):
        # BRIEF-FR-006 E23: every source this order registered or corrected must carry a
        # policy_status and a last_policy_reviewed date (2026-09-03).
        e23_source_ids = {
            "hacker_news_who_is_hiring", "reddit_forhire", "reddit_remotejobs",
            "reddit_machinelearningjobs", "reddit_datajobs", "reddit_hiring", "reddit_jobbit",
            "reddit_bigdatajobs", "ycombinator_work_at_a_startup", "working_nomads", "remote_co",
            "justremote", "wellfound", "arc_dev", "ai_jobs_net", "otta", "peopleperhour",
            "preply", "superprof", "wyzant", "tutor_com", "chegg", "cambly",
            # pre-existing entries this order corrected/updated with a dated 2026-09-03 review:
            "freelancer", "linkedin", "indeed", "wuzzuf", "bayt", "naukrigulf", "gulftalent",
            "upwork", "mostaql", "khamsat", "contra", "toptal", "jobicy",
        }
        data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
        by_id = {entry["source_id"]: entry for entry in data.get("sources", [])}
        missing = e23_source_ids - set(by_id)
        self.assertEqual(set(), missing, f"E23 source ids missing from the registry entirely: {missing}")
        for source_id in sorted(e23_source_ids):
            entry = by_id[source_id]
            with self.subTest(source_id=source_id):
                self.assertTrue(entry.get("policy_status"), "policy_status must be set")
                reviewed = entry.get("last_policy_reviewed")
                self.assertIsNotNone(reviewed, "last_policy_reviewed must be set")
                self.assertEqual(str(reviewed), "2026-09-02" if source_id == "jobicy" else "2026-09-03")

    def test_hacker_news_is_the_only_new_e23_source_bound_to_an_adapter(self):
        # Guards against accidentally wiring a manual_only/platform_application source
        # (e.g. a Reddit route or a tutoring platform) into the live adapter pipeline.
        new_e23_bound = {
            adapter.source_id for adapter in get_all_standard_adapters()
        } & {
            "hacker_news_who_is_hiring", "reddit_forhire", "reddit_remotejobs",
            "reddit_machinelearningjobs", "reddit_datajobs", "reddit_hiring",
            "reddit_jobbit", "reddit_bigdatajobs", "preply", "superprof", "wyzant",
            "tutor_com", "chegg", "cambly",
        }
        self.assertEqual({"hacker_news_who_is_hiring"}, new_e23_bound)


if __name__ == "__main__":
    unittest.main()
