# Supabase runtime contract (W17)

`storage.supabase_runtime.render_runtime_sql()` emits the provider-neutral
interactive boundary after the Alembic head. It is deterministic and contains
no credentials or Founder payloads.

The generated view exposes only persisted `feed_projection` rows. Poll Now is
an asynchronous insert into the durable `worker_jobs` queue and status is read
through a separate RPC. Neither path evaluates, polls, or rebuilds the corpus.

Browser access is fail closed. Migration `0010_hosted_runtime` binds the
Supabase JWT subject to the durable singleton `founder_identity` row and grants
the `authenticated` role only when that binding matches. An absent binding
denies access. Anonymous access and public function execution are revoked.

Apply the generated SQL only after the repository Alembic head and verify the
required tables with `assert_runtime_schema_capabilities()`. A real Supabase
execution, Founder subject binding, and browser RLS proof remain provider
operations and are not claimed by repository tests.
