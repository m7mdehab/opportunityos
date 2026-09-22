from __future__ import annotations

from pathlib import Path
import subprocess


def test_deleted_supabase_project_reference_is_absent_from_active_repository_files() -> None:
    root = Path(__file__).resolve().parents[1]
    tracked_paths = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root
    ).decode("utf-8").split("\0")
    deleted_ref = "lrrcpwaapwynzdsxz" + "why"
    violations: list[str] = []

    for relative in filter(None, tracked_paths):
        normalized = relative.replace("\\", "/")
        if normalized.startswith("reports/evidence/"):
            continue
        path = root / relative
        try:
            contents = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if deleted_ref in contents:
            violations.append(normalized)

    assert not violations, f"deleted Supabase project reference remains active: {violations}"
