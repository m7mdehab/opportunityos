"""Tests for truth.pack: founder truth pack loading and reporting.

All tests use explicit temporary paths. None of these tests read, write, or
list anything under private/ -- the DEFAULT_TRUTH_PACK_PATH constant is
exercised only as a value, never dereferenced against the real filesystem.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from truth.pack import (
    DEFAULT_TRUTH_PACK_PATH,
    LoadedPack,
    TruthPackInvalid,
    TruthPackMissing,
    TruthPackVerificationError,
    load_founder_pack,
    load_truth_pack,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "docs" / "templates" / "truth_pack.template.yaml"
TRUTH_CHECK_SCRIPT = REPO_ROOT / "scripts" / "truth_check.py"

# Distinctive, obviously-synthetic values that appear in the shipped
# template. If any of these ever show up in truth_check.py's output, the
# script is leaking field values.
TEMPLATE_DISTINCTIVE_VALUES = (
    "Jane Q. Example",
    "Example Industries Ltd",
    "Senior Widget Engineer",
    "Certified Widget Professional",
    "Widget Design",
    "Example State University",
)


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def _minimal_pack_yaml(*, reason: str = "keep it honest", key_order: str = "forward") -> str:
    """A small, self-contained pack that loads cleanly.

    `key_order` == "reversed" reorders mapping keys (but not list contents)
    relative to "forward", to prove the truth_pack_hash does not depend on
    incidental key ordering.
    """
    if key_order == "forward":
        evidence_block = (
            '  - id: ev-role\n'
            '    content: "Example Engineer at Example Org from 2024-01-01"\n'
            '    source: "fixture"\n'
            '    locator: "employment.0"\n'
            '    metadata: {"organization": "Example Org", "title": "Example Engineer"}\n'
        )
        employment_block = (
            '    - id: job-example\n'
            '      organization: "Example Org"\n'
            '      title: "Example Engineer"\n'
            '      start_date: "2024-01-01"\n'
            '      evidence_ids: ["ev-role"]\n'
        )
    else:
        evidence_block = (
            '  - id: ev-role\n'
            '    locator: "employment.0"\n'
            '    source: "fixture"\n'
            '    metadata: {"title": "Example Engineer", "organization": "Example Org"}\n'
            '    content: "Example Engineer at Example Org from 2024-01-01"\n'
        )
        employment_block = (
            '    - id: job-example\n'
            '      evidence_ids: ["ev-role"]\n'
            '      start_date: "2024-01-01"\n'
            '      title: "Example Engineer"\n'
            '      organization: "Example Org"\n'
        )

    return (
        "evidence:\n"
        f"{evidence_block}"
        "career_profile:\n"
        "  id: career-example\n"
        "  employment:\n"
        f"{employment_block}"
        "  red_lines:\n"
        "    - id: redline-1\n"
        '      pattern: "test pattern"\n'
        f'      reason: "{reason}"\n'
    )


class LoadFounderPackMissingTest(unittest.TestCase):
    def test_missing_file_raises_truth_pack_missing(self):
        with TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "does-not-exist.yaml"
            with self.assertRaises(TruthPackMissing):
                load_founder_pack(missing_path)


class LoadFounderPackInvalidTest(unittest.TestCase):
    def test_invalid_pack_raises_truth_pack_invalid_with_findings(self):
        with TemporaryDirectory() as tmp:
            path = _write(
                Path(tmp), "broken.yaml",
                "evidence:\n"
                "  - id: ev-role\n"
                '    content: "Example Engineer at Example Org from 2024-01-01"\n'
                '    source: "fixture"\n'
                '    locator: "employment.0"\n'
                "career_profile:\n"
                "  id: career-example\n"
                "  employment:\n"
                "    - id: job-example\n"
                '      organization: "Example Org"\n'
                '      title: "Example Engineer"\n'
                '      start_date: "2024-01-01"\n'
                '      evidence_ids: ["ev-nonexistent"]\n',
            )
            with self.assertRaises(TruthPackInvalid) as ctx:
                load_founder_pack(path)
            self.assertTrue(ctx.exception.findings)
            self.assertIn("ev-nonexistent", ctx.exception.findings[0])


class LoadFounderPackDefaultPathTest(unittest.TestCase):
    def test_default_path_constant_is_private_truth_pack(self):
        self.assertEqual(Path("private/truth_pack.yaml"), DEFAULT_TRUTH_PACK_PATH)


class LoadFounderPackHashTest(unittest.TestCase):
    def test_hash_stable_across_two_loads_of_same_file(self):
        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "pack.yaml", _minimal_pack_yaml())
            first = load_founder_pack(path)
            second = load_founder_pack(path)
            self.assertEqual(first.truth_pack_hash, second.truth_pack_hash)

    def test_hash_stable_across_key_ordering(self):
        with TemporaryDirectory() as tmp:
            forward = _write(Path(tmp), "forward.yaml", _minimal_pack_yaml(key_order="forward"))
            reversed_ = _write(Path(tmp), "reversed.yaml", _minimal_pack_yaml(key_order="reversed"))
            forward_pack = load_founder_pack(forward)
            reversed_pack = load_founder_pack(reversed_)
            self.assertEqual(forward_pack.truth_pack_hash, reversed_pack.truth_pack_hash)

    def test_hash_changes_when_content_changes(self):
        with TemporaryDirectory() as tmp:
            path_a = _write(Path(tmp), "a.yaml", _minimal_pack_yaml(reason="keep it honest"))
            path_b = _write(Path(tmp), "b.yaml", _minimal_pack_yaml(reason="a materially different reason"))
            pack_a = load_founder_pack(path_a)
            pack_b = load_founder_pack(path_b)
            self.assertNotEqual(pack_a.truth_pack_hash, pack_b.truth_pack_hash)


class LoadFounderPackReportTest(unittest.TestCase):
    def test_report_and_loaded_pack_shape(self):
        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "pack.yaml", _minimal_pack_yaml())
            loaded = load_founder_pack(path)
            self.assertIsInstance(loaded, LoadedPack)
            self.assertTrue(loaded.report.valid)
            self.assertEqual((), loaded.report.findings)
            counts = dict(loaded.report.section_counts)
            self.assertEqual(1, counts["evidence"])
            self.assertEqual(1, counts["career_profile"])
            self.assertEqual(1, counts["career_profile.employment"])
            self.assertEqual(0, counts["career_profile.education"])
            self.assertIn("career_profile.education", loaded.report.empty_sections())


class TruthPackTemplateTest(unittest.TestCase):
    """The shipped template must load cleanly, as-is, with zero errors."""

    def test_template_loads_with_zero_validator_errors(self):
        self.assertTrue(TEMPLATE_PATH.exists(), f"template missing at {TEMPLATE_PATH}")
        loaded = load_founder_pack(TEMPLATE_PATH)
        self.assertTrue(loaded.report.valid)
        self.assertEqual((), loaded.report.findings)
        self.assertTrue(loaded.truth_pack_hash)

    def test_template_covers_every_documented_section(self):
        loaded = load_founder_pack(TEMPLATE_PATH)
        counts = dict(loaded.report.section_counts)
        self.assertEqual(1, counts["career_profile"])
        self.assertEqual(1, counts["capability_profile"])
        for name, count in counts.items():
            self.assertGreater(count, 0, f"template section {name} is unexpectedly empty")


class TruthPackTemplateArtifactGenerationKnownLimitationTest(unittest.TestCase):
    """Characterises a known, out-of-scope limitation: tailored-document
    generation from the *shipped* template's own synthetic data is refused
    by `ClaimValidator` for at least one generated claim, and this is
    correct, safe behaviour -- not a bug this template or `truth/validator.py`
    can fix.

    This is deliberately NOT a "zero rejected claims" test. Investigation
    during BRIEF-FR-004 D5 found two independent, structural reasons the
    compiler's generated claims are refused, neither of which a truth pack's
    *data* can resolve:

      1. Relational composition (`TruthGraph.are_relationally_linked`,
         `truth/graph.py`). A composite claim -- one whose cited evidence
         spans more than one profile entity, such as a CV "Professional
         Summary" naming both a job title and a skill -- is refused unless
         those entities are connected by an explicit `TypedRelation` or a
         shared non-root entity. Adding such a relation via this file's
         top-level `relations:` section does not work today: `TruthGraph`
         (built by `truth.ingest.graph_from_dict`) processes `relations:`
         *before* `career_profile`/`capability_profile` are added, so a
         relation naming a profile entity id such as `job-example-1` fails
         to load with "references nonexistent source" -- the entity does
         not exist yet at that point. This is an ingest ordering bug in
         `truth/ingest.py`, not a property of the template format; fixing
         the ordering is in scope for `truth/ingest.py`, which is frozen
         for this work.
      2. Material lexical coverage (`truth/validator.py`, the check
         immediately after the relational-composition guard). Even for a
         single-evidence claim, every non-trivial word the compiler writes
         must appear verbatim in the cited evidence. The compiler's prose
         is fixed (`matching/compiler_employment.py` is frozen for this
         work) and includes connective phrasing ("professional",
         "background", "verified", "competencies") that the founder's
         evidence -- which describes what happened to them, not the
         sentence the compiler will eventually write about it -- will not
         literally contain. This is a property of how `ClaimValidator`
         checks whole rendered sentences rather than the underlying facts;
         fixing it is in scope for `truth/validator.py`, which is frozen
         for this work. The cover letter is structurally worse regardless
         of that fix: its generated sentences name the *target
         opportunity's own* job title and organization, which can never
         appear in the founder's own evidence by construction, for any
         opportunity -- no change to the template's data can make a cover
         letter's employer-naming sentence self-evidencing.

    No change to the template's *data* can force a 0-rejected result while
    keeping the CV's Professional Summary and the cover letter honest. (A
    graph that omits the employment record entirely -- as
    `web/tests/e2e/truth_pack.e2e.yaml` and
    `api/test_api.py::_clean_truth_pack_graph()` both do -- does reach zero
    rejections, because the compiler never builds the composite summary
    claim in the first place; that is not a counter-example to the claim
    above, and it is not a usable outcome for a founder, since a CV with no
    job history is not a CV.) Writing the compiler's own vocabulary into
    the template's evidence text to force approval would fabricate
    provenance to match generated prose, which AGENTS.md's first Hard Rule
    forbids ("Never fabricate a claim about the founder"), so this test
    does not attempt it. Instead it proves the *refusal* path is correct
    and safe: every rejection carries a concrete, non-empty reason, and a
    rejected claim never reaches document export.
    """

    def test_shipped_template_claim_rejections_are_reasoned_and_block_export(self):
        from matching.binary_export import BinaryArtifactExporter
        from matching.compiler_employment import EmploymentArtifactCompiler
        from opportunity.adapters.himalayas import HimalayasAdapter
        from opportunity.transport import DiscoveryRequest, MockTransport, TransportResponse
        from truth.validator import ClaimValidator

        # Fixture opportunity, fetched only through the offline MockTransport
        # -- no network access, ever -- exactly as
        # storage/test_postgres_integration.py's Case U does.
        fixture_path = REPO_ROOT / "opportunity" / "fixtures" / "himalayas.json"
        payload = fixture_path.read_text(encoding="utf-8")
        transport = MockTransport(
            {"himalayas": TransportResponse(status_code=200, body=payload, latency_ms=5)}
        )
        adapter = HimalayasAdapter()
        response = transport.fetch(DiscoveryRequest(source_id="himalayas", url=adapter.feed_url))
        self.assertTrue(response.is_success)
        parsed = adapter.parse_payload(
            response.body, raw_pointer="fixture:himalayas", fetched_at="2026-01-01T00:00:00Z"
        )
        self.assertTrue(parsed.opportunities, "fixture must parse to at least one opportunity")
        opportunity = parsed.opportunities[0]

        loaded = load_founder_pack(TEMPLATE_PATH)
        graph = loaded.graph
        compiler = EmploymentArtifactCompiler()
        validator = ClaimValidator(graph)

        saw_rejection = False
        for artifact in (
            compiler.compile_tailored_cv(opportunity, graph),
            compiler.compile_cover_letter(opportunity, graph),
        ):
            self.assertTrue(artifact.generated_claims, "artifact produced no claims to validate")

            findings = []
            for claim in artifact.generated_claims:
                result = validator.validate_claim(claim.text, claim.evidence_ids)
                if not result.allowed:
                    saw_rejection = True
                    findings.append(result)
                    # A refusal with no stated reason would be as unsafe as
                    # a silent one -- the founder must be able to see why.
                    self.assertTrue(result.reasons, f"rejected claim has no reason: {claim.text!r}")
                    for reason in result.reasons:
                        self.assertTrue(reason.strip())

            # Mirrors api/routes_api.py::_compile_and_export's own gate:
            # export_to_docx is only ever called once every claim is allowed.
            # This test does not re-derive that gate itself -- the real API
            # gate (a 409, and a body that never starts with the docx `PK`
            # zip signature) is asserted in
            # ArtifactRoutesTest.test_artifact_409_never_returns_docx_bytes.
            if not findings:
                docx_bytes = BinaryArtifactExporter.export_to_docx(artifact)
                self.assertTrue(docx_bytes)

        self.assertTrue(
            saw_rejection,
            "expected the shipped template to still exercise the claim validator's refusal "
            "path for at least one generated claim -- see class docstring for why this is "
            "correct, and why it cannot be closed by editing template data",
        )


class TruthCheckScriptTest(unittest.TestCase):
    def _run(self, path: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TRUTH_CHECK_SCRIPT), "--path", str(path)],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        )

    def test_template_copy_exits_zero(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "tp.yaml"
            path.write_text(TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            result = self._run(path)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_broken_copy_exits_one_with_findings(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "tp.yaml"
            broken = TEMPLATE_PATH.read_text(encoding="utf-8").replace(
                'state: "completed"', 'state: "bogus_state"'
            )
            self.assertIn('state: "bogus_state"', broken)
            path.write_text(broken, encoding="utf-8")
            result = self._run(path)
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("INVALID", result.stdout)
            self.assertIn("finding:", result.stdout)

    def test_output_contains_no_template_field_values(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "tp.yaml"
            path.write_text(TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            result = self._run(path)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            for value in TEMPLATE_DISTINCTIVE_VALUES:
                self.assertNotIn(value, result.stdout)
                self.assertNotIn(value.lower(), result.stdout.lower())


class LoadTruthPackRemoteAndIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.yaml_content = _minimal_pack_yaml()
        self.raw_bytes = self.yaml_content.encode("utf-8")
        import hashlib
        self.raw_hash = hashlib.sha256(self.raw_bytes).hexdigest()

    def test_load_truth_pack_from_http_success(self):
        import io
        from unittest import mock
        from urllib.error import HTTPError

        mock_resp = io.BytesIO(self.raw_bytes)
        mock_resp.headers = {"Content-Type": "application/x-yaml"}

        with mock.patch("truth.pack.urlopen", return_value=mock_resp) as mock_urlopen:
            loaded = load_truth_pack("https://storage.supabase.co/v1/object/authenticated/truth/pack.yaml")
            self.assertIsInstance(loaded, LoadedPack)
            self.assertTrue(loaded.report.valid)
            self.assertEqual(64, len(loaded.truth_pack_hash))
            mock_urlopen.assert_called_once()

    def test_load_truth_pack_http_auth_token_header(self):
        import io
        from unittest import mock

        mock_resp = io.BytesIO(self.raw_bytes)
        mock_resp.headers = {"Content-Type": "application/x-yaml"}

        with mock.patch("truth.pack.urlopen", return_value=mock_resp) as mock_urlopen:
            tok = "val-tok"
            loaded = load_truth_pack(
                "https://api.example.com/truth_pack.yaml",
                auth_token=tok,
            )
            self.assertIsInstance(loaded, LoadedPack)
            req = mock_urlopen.call_args[0][0]
            self.assertEqual("Bearer val-tok", req.headers.get("Authorization"))

    def test_load_truth_pack_http_404_raises_truth_pack_missing(self):
        from unittest import mock
        from urllib.error import HTTPError

        err = HTTPError("https://api.example.com/pack.yaml", 404, "Not Found", {}, None)
        with mock.patch("truth.pack.urlopen", side_effect=err):
            with self.assertRaises(TruthPackMissing):
                load_truth_pack("https://api.example.com/pack.yaml")

    def test_load_truth_pack_http_403_raises_truth_pack_invalid(self):
        from unittest import mock
        from urllib.error import HTTPError

        err = HTTPError("https://api.example.com/pack.yaml", 403, "Forbidden", {}, None)
        with mock.patch("truth.pack.urlopen", side_effect=err):
            with self.assertRaises(TruthPackInvalid) as ctx:
                load_truth_pack("https://api.example.com/pack.yaml")
            self.assertIn("HTTP 403", str(ctx.exception))

    def test_load_truth_pack_data_uri_plain_and_base64(self):
        import base64
        import urllib.parse

        # Plain data URI
        plain_uri = f"data:text/yaml,{urllib.parse.quote(self.yaml_content)}"
        loaded_plain = load_truth_pack(plain_uri)
        self.assertIsInstance(loaded_plain, LoadedPack)

        # Base64 data URI
        b64_payload = base64.b64encode(self.raw_bytes).decode("ascii")
        b64_uri = f"data:application/x-yaml;base64,{b64_payload}"
        loaded_b64 = load_truth_pack(b64_uri)
        self.assertIsInstance(loaded_b64, LoadedPack)
        self.assertEqual(loaded_plain.truth_pack_hash, loaded_b64.truth_pack_hash)

    def test_load_truth_pack_integrity_hash_verification(self):
        import urllib.parse

        quoted_uri = f"data:text/yaml,{urllib.parse.quote(self.yaml_content)}"
        # 1. Matching raw SHA-256 succeeds
        loaded = load_truth_pack(
            quoted_uri,
            expected_hash=self.raw_hash,
        )
        self.assertIsInstance(loaded, LoadedPack)

        # 2. Matching canonical graph hash succeeds
        canonical_hash = loaded.truth_pack_hash
        loaded_by_canonical = load_truth_pack(
            quoted_uri,
            expected_hash=canonical_hash,
        )
        self.assertEqual(canonical_hash, loaded_by_canonical.truth_pack_hash)

        # 3. Mismatched hash raises TruthPackVerificationError (and TruthPackInvalid)
        bogus_hash = "0" * 64
        with self.assertRaises(TruthPackVerificationError) as ctx:
            load_truth_pack(
                quoted_uri,
                expected_hash=bogus_hash,
            )
        self.assertIsInstance(ctx.exception, TruthPackInvalid)
        self.assertIn("integrity verification failed", str(ctx.exception))

    def test_load_truth_pack_cloud_mode_rejects_local_path(self):
        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "pack.yaml", self.yaml_content)
            with self.assertRaises(TruthPackInvalid) as ctx:
                load_truth_pack(path, allow_local_path=False)
            self.assertIn("local filesystem paths not allowed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
