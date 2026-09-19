-- Read-only schema verification for FR-007 Supabase execution.
SELECT current_database() AS database_name,
       current_user AS current_user_name,
       current_setting('server_version_num') AS server_version_num;
SELECT version_num FROM public.alembic_version ORDER BY version_num;
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'public' ORDER BY table_name;
SELECT table_name, constraint_name, constraint_type
  FROM information_schema.table_constraints
 WHERE table_schema = 'public'
 ORDER BY table_name, constraint_name;
