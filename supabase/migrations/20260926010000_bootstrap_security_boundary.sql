-- Coordination Engine security boundary.
-- Applied migrations are immutable; corrections use a later timestamped migration.

create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

create schema if not exists app;
create schema if not exists app_private;

revoke all on schema app from public, anon, authenticated, service_role;
revoke all on schema app_private from public, anon, authenticated, service_role;

do $roles$
begin
  if not exists (select 1 from pg_roles where rolname = 'coordination_api') then
    create role coordination_api
      nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'coordination_worker') then
    create role coordination_worker
      nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
  end if;

  if exists (
    select 1
    from pg_roles
    where rolname in ('coordination_api', 'coordination_worker')
      and (rolcanlogin or rolsuper or rolcreatedb or rolcreaterole or rolinherit or rolbypassrls)
  ) then
    raise exception 'coordination runtime roles exist with unsafe attributes';
  end if;
end
$roles$;

-- PostgreSQL 16+ separates role membership from permission to SET ROLE. The migration
-- operator may assume the runtime roles for verification, but never inherits them implicitly.
grant coordination_api, coordination_worker to current_user
  with inherit false, set true;

grant usage on schema app to coordination_api, coordination_worker;

alter default privileges in schema app revoke all on tables from public, anon, authenticated, service_role;
alter default privileges in schema app revoke all on sequences from public, anon, authenticated, service_role;
alter default privileges in schema app revoke execute on functions from public, anon, authenticated, service_role;
alter default privileges in schema app_private revoke all on tables from public, anon, authenticated, service_role;
alter default privileges in schema app_private revoke execute on functions from public, anon, authenticated, service_role;

create table app_private.migration_contract (
  version text primary key check (version ~ '^[0-9]{14}$'),
  name text not null,
  repository_commit text null check (repository_commit ~ '^[0-9a-f]{40}$'),
  environment_label text null,
  installed_at timestamptz not null default clock_timestamp(),
  installed_by name not null default current_user
);

revoke all on table app_private.migration_contract from public, anon, authenticated, service_role;

create or replace function app.current_actor_id()
returns uuid
language sql
stable
parallel safe
set search_path = pg_catalog
as $$
  select nullif(current_setting('app.actor_id', true), '')::uuid
$$;

create or replace function app.current_company_id()
returns uuid
language sql
stable
parallel safe
set search_path = pg_catalog
as $$
  select nullif(current_setting('app.company_id', true), '')::uuid
$$;

create or replace function app.current_purpose()
returns text
language sql
stable
parallel safe
set search_path = pg_catalog
as $$
  select nullif(current_setting('app.purpose', true), '')
$$;

create or replace function app.request_context_present()
returns boolean
language sql
stable
parallel safe
set search_path = pg_catalog, app
as $$
  select app.current_actor_id() is not null
     and app.current_company_id() is not null
     and app.current_purpose() is not null
$$;

create or replace function app.touch_updated_row()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
  new.updated_at := clock_timestamp();
  new.row_version := old.row_version + 1;
  return new;
end
$$;

revoke execute on function app.current_actor_id() from public;
revoke execute on function app.current_company_id() from public;
revoke execute on function app.current_purpose() from public;
revoke execute on function app.request_context_present() from public;
revoke execute on function app.touch_updated_row() from public;
grant execute on function app.current_actor_id() to coordination_api, coordination_worker;
grant execute on function app.current_company_id() to coordination_api, coordination_worker;
grant execute on function app.current_purpose() to coordination_api, coordination_worker;
grant execute on function app.request_context_present() to coordination_api, coordination_worker;

insert into app_private.migration_contract (version, name)
values ('20260926010000', 'bootstrap_security_boundary');
