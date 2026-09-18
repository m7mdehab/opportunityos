# FR-007 Work Split

Current parallel split:

- `W0.3` — provider-neutral runtime configuration contract: bounded implementer/Codex task.
- `W1.1/W1.2` — persisted feed projection and SQL-native query path: Owner/Overseer architecture-sensitive track.

These tracks are intentionally file- and concern-disjoint. W0.3 must not touch business/runtime code; W1 must not depend on provider provisioning or W0.3 completion.