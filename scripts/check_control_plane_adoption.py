#!/usr/bin/env python3
"""Structural Control Plane v2.1 adoption check using only Python stdlib."""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "CONTROL_PLANE.yaml"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def parse_simple_yaml(text: str) -> dict:
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    list_context: tuple[int, dict, str] | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if line.startswith("- "):
            if list_context is None or indent <= list_context[0]:
                fail(f"invalid list item: {line}")
            container, key = list_context[1], list_context[2]
            container[key].append(line[2:].strip().strip('"\''))
            continue
        list_context = None
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if ":" not in line:
            fail(f"invalid yaml line: {line}")
        key, raw_value = line.split(":", 1)
        key, value = key.strip(), raw_value.strip()
        if value == "":
            if key == "amendments":
                parent[key] = []
                list_context = (indent, parent, key)
            else:
                node: dict = {}
                parent[key] = node
                stack.append((indent, node))
            continue
        if value.lower() in {"true", "false"}:
            parent[key] = value.lower() == "true"
        else:
            parent[key] = value.strip('"\'')
    return root


def get(cfg: dict, *keys: str):
    cur = cfg
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            fail("missing CONTROL_PLANE.yaml key: " + ".".join(keys))
        cur = cur[key]
    return cur


def require_path(path_value: str, label: str) -> Path:
    path = ROOT / path_value
    if not path.exists():
        fail(f"{label} path does not exist: {path_value}")
    return path


def main() -> int:
    if not CFG.exists(): fail("CONTROL_PLANE.yaml missing")
    cfg = parse_simple_yaml(CFG.read_text(encoding="utf-8"))
    if get(cfg, "control_plane", "repository") != "m7mdehab/ai-engineering-control-plane": fail("wrong control-plane repository")
    if get(cfg, "control_plane", "baseline") != "AI_ENGINEERING_OPERATING_SYSTEM_v2.0.md": fail("unexpected control-plane baseline")
    if "AI_ENGINEERING_OPERATING_SYSTEM_v2.0.1_ADDENDUM.md" not in get(cfg, "control_plane", "amendments"): fail("v2.0.1 addendum not declared")
    if get(cfg, "control_plane", "operations_layer") != "CONTROL_PLANE_OPERATIONS_v2.1.md": fail("v2.1 operations layer not declared")
    sha = str(get(cfg, "control_plane", "last_verified_control_plane_sha"))
    if not re.fullmatch(r"[0-9a-f]{40}", sha): fail("last_verified_control_plane_sha must be a verified 40-char SHA")
    paths = {"agents": get(cfg,"project","agents"), "authority_index": get(cfg,"project","authority_index"), "chat_resume": get(cfg,"project","chat_resume"), "state": get(cfg,"project","state"), "architecture": get(cfg,"project","architecture"), "roadmap": get(cfg,"project","roadmap"), "session_commands": get(cfg,"operations","session_commands"), "context_integrity_check": get(cfg,"operations","context_integrity_check")}
    resolved = {name: require_path(str(value), name) for name, value in paths.items()}
    agents_text = resolved["agents"].read_text(encoding="utf-8")
    if "m7mdehab/ai-engineering-control-plane" not in agents_text or "Owner/Overseer" not in agents_text or "Master" not in agents_text: fail("AGENTS.md does not preserve canonical control-plane hierarchy")
    for shim in (ROOT/"CLAUDE.md", ROOT/"GEMINI.md", ROOT/".github/copilot-instructions.md"):
        if shim.exists() and "AGENTS.md" not in shim.read_text(encoding="utf-8"): fail(f"provider shim does not route to AGENTS.md: {shim.relative_to(ROOT)}")
    for glob_key in ("active_brief_glob","report_glob"):
        pattern = str(get(cfg,"project",glob_key))
        if not glob.glob(str(ROOT/pattern)): fail(f"project.{glob_key} resolves to no files: {pattern}")
    commands = resolved["session_commands"].read_text(encoding="utf-8")
    for required in ("RESUME","COMPACT","MASTER"):
        if required not in commands: fail(f"SESSION_COMMANDS.md missing {required}")
    if re.search(r"\b[0-9a-f]{40}\b", commands): fail("SESSION_COMMANDS.md contains a mutable commit SHA")
    for key in ("closeout_requires_canonical_reconciliation","least_expensive_capable_executor","direct_cross_provider_invocation_requires_runtime_capability","github_handoff_when_direct_invocation_unavailable"):
        if get(cfg,"operations",key) is not True: fail(f"operations.{key} must be enabled")
    secret_patterns = [re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), re.compile(r"(?i)\b(password|api[_-]?key|secret|access[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}")]
    for path in [CFG,resolved["agents"],resolved["authority_index"],resolved["chat_resume"],resolved["session_commands"]]:
        text = path.read_text(encoding="utf-8")
        if any(p.search(text) for p in secret_patterns): fail(f"possible credential material in canonical boot file: {path.relative_to(ROOT)}")
    print("PASS: Control Plane Operations Layer v2.1 structural adoption is coherent")
    print(f"verified_control_plane_sha={sha}")
    return 0

if __name__ == "__main__": sys.exit(main())
