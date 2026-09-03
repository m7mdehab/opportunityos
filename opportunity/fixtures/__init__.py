"""Loader for the A1C fixture corpus.

Each fixture file under ``opportunity/fixtures/corpus/<source_slug>/NNN.json`` stores one
real, publicly captured posting as ``{"source_id", "request_url", "fetched_at", "raw_body"}``.
``raw_body`` is the record wrapped in the minimal feed envelope its adapter's
``parse_payload`` expects (e.g. ``{"jobs": [job]}`` for Greenhouse), so every fixture stays
independently re-parseable by the existing, unmodified adapters.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"


@dataclass(frozen=True, slots=True)
class CorpusFixture:
    source_id: str
    request_url: str
    fetched_at: str
    raw_body: str
    path: Path


def iter_corpus(corpus_dir: Path | None = None) -> Iterator[CorpusFixture]:
    """Yield every captured fixture, sorted for deterministic iteration."""
    root = corpus_dir or CORPUS_DIR
    if not root.exists():
        return
    for source_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for fixture_path in sorted(source_dir.glob("*.json")):
            data = json.loads(fixture_path.read_text(encoding="utf-8"))
            yield CorpusFixture(
                source_id=data["source_id"],
                request_url=data["request_url"],
                fetched_at=data["fetched_at"],
                raw_body=data["raw_body"],
                path=fixture_path,
            )


def load_corpus(corpus_dir: Path | None = None) -> list[CorpusFixture]:
    return list(iter_corpus(corpus_dir))
