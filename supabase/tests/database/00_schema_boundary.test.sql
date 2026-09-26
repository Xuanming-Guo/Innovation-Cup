begin;
select plan(20);

select has_schema('app', 'private application schema exists');
select has_schema('app_private', 'private operational schema exists');
select has_table('app', 'companies', 'companies table exists');
select has_table('app', 'user_profiles', 'global user profiles table exists');
select has_table('app', 'company_memberships', 'company memberships table exists');
select has_table('app', 'teams', 'teams table exists');
select has_table('app', 'employee_profiles', 'employee profiles table exists');
select has_table('app', 'team_memberships', 'team memberships table exists');
select has_table('app', 'invitations', 'invitations table exists');
select has_table('app', 'source_records', 'source records table exists');
select has_table('app', 'source_versions', 'source versions table exists');
select has_table('app', 'source_access_grants', 'source access grants table exists');
select has_table('app', 'private_files', 'private files table exists');

select ok(
  (
    select bool_and(class.relrowsecurity)
    from pg_class as class
    join pg_namespace as namespace on namespace.oid = class.relnamespace
    where namespace.nspname = 'app'
      and class.relkind = 'r'
      and class.relname <> 'migration_contract'
  ),
  'every application table has RLS enabled'
);

select ok(
  exists (
    select 1 from pg_roles
    where rolname = 'coordination_api'
      and not rolcanlogin and not rolsuper and not rolbypassrls
  ),
  'API role is a non-login, non-superuser, non-BYPASSRLS role'
);

select ok(
  exists (
    select 1 from pg_roles
    where rolname = 'coordination_worker'
      and not rolcanlogin and not rolsuper and not rolbypassrls
  ),
  'worker role is a non-login, non-superuser, non-BYPASSRLS role'
);

select ok(
  not exists (
    select 1
    from information_schema.role_table_grants
    where table_schema = 'app'
      and grantee in ('PUBLIC', 'anon', 'authenticated', 'service_role')
  ),
  'Data API roles have no application table privileges'
);

select ok(
  not exists (
    select 1
    from pg_class as class
    join pg_namespace as namespace on namespace.oid = class.relnamespace
    where namespace.nspname = 'app'
      and class.relkind = 'r'
      and pg_get_userbyid(class.relowner) in ('coordination_api', 'coordination_worker')
  ),
  'runtime roles own no application tables'
);

select is(
  (select count(*)::integer from app_private.migration_contract),
  6,
  'all ordered repository migrations registered their version'
);

select ok(
  not exists (
    select 1
    from pg_proc as procedure
    join pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname in ('app', 'app_private')
      and procedure.prosecdef
      and not exists (
        select 1 from unnest(coalesce(procedure.proconfig, array[]::text[])) as setting
        where setting like 'search_path=%'
      )
  ),
  'every security-definer function fixes its search path'
);

select * from finish();
rollback;
