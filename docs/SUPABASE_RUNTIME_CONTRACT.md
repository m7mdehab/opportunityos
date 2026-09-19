# Supabase runtime contract (W17)

`storage.supabase_runtime.render_runtime_sql()` emits the provider-neutral
interactive boundary after the Alembic head. It is deterministic and contains
no credentials or Founder payloads.

The generated view exposes only persisted `feed_projection` rows. Poll Now is
an asynchronous insert into the durable `worker_jobs` queue and status is read
through a separate RPC. Neither path evaluates, polls, or rebuilds the corpus.

Browser access is fail closed. The SQL grants the `authenticated` role only
when its JWT subject equals the database setting
`app.founder_auth_uid`; an unset setting denies access. The setting must be
configured by the provider owner through a secure database session and is not
committed here. Anonymous access and public function execution are revoked.

Apply the generated SQL only after the repository Alembic head and verify the
required tables with `assert_runtime_schema_capabilities()`. A real Supabase
execution, Founder subject binding, and browser RLS proof remain provider
operations and are not claimed by repository tests.
