# Assistant Interoperability

- **Claude Code** has the private repository and local working copy. It reads `CLAUDE.md`, whose first line imports `AGENTS.md`.
- **ChatGPT / Codex** reads the private repository through its GitHub connector and reads `AGENTS.md` natively. It has full repository access.
- **Claude chat** can clone only the public mirror and is read-only. It sees documentation, briefs, and reports. It does not see code.

Because Claude chat cannot see code, it can verify report consistency, acceptance-criterion coverage, source-registry evidence, state freshness, and ADR discipline, but it cannot verify that implementation matches the report. Claude Code checker agents and CI carry that part of the maker/checker burden.

All three assistants read `docs/STATE.md` before advising. No assistant is authoritative over a committed ADR. If assistants disagree, the ADR log settles the issue; if no ADR applies, write one.

`CLAUDE.md` could instead be created with `ln -s AGENTS.md CLAUDE.md`, but OpportunityOS uses Claude's `@AGENTS.md` import so Claude-specific notes can remain separate without duplicating vendor-neutral rules.
