"""Generate an encoded Founder password hash without exposing the password."""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.security import hash_founder_password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    first = getpass.getpass("Input: ")
    second = getpass.getpass("Confirm: ")
    if first != second:
        print("password confirmation failed", file=sys.stderr)
        return 2
    try:
        print(hash_founder_password(first))
    except ValueError as exc:
        print(f"invalid password: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
