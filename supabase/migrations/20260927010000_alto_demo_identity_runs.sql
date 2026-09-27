-- ALTO DB01: existing Auth identity is distinct from synthetic scenario people.
alter table app.employee_profiles
  alter column membership_id drop not null,
  add column profile_kind text not null default 'member'
    check (profile_kind in ('member', 'synthetic')),
  add column synthetic_key text,
  add column display_name text check (length(btrim(display_name)) between 1 and 120),
  add column title text check (length(title) <= 160),
  add column function_key text check (function_key in ('engineering','design','qa','marketing','support','leadership')),
  add column scenario_detail text not null default 'rich' check (scenario_detail in ('rich','background')),
  add constraint employee_profile_identity_form check (
    (profile_kind = 'member' and membership_id is not null and synthetic_key is null)
    or (profile_kind = 'synthetic' and membership_id is null
      and synthetic_key ~ '^[a-z][a-z0-9_-]{0,63}$' and display_name is not null)),
  add unique (company_id, synthetic_key);

create function app.guard_synthetic_employee() returns trigger
language plpgsql security definer set search_path = pg_catalog, app as $$
begin
  if new.profile_kind = 'synthetic' and not exists (
    select 1 from app.companies where id = new.company_id and is_demo
  ) then raise exception using errcode='23514', message='synthetic_company_required'; end if;
  return new;
end $$;
create trigger employee_synthetic_guard before insert or update on app.employee_profiles
  for each row execute function app.guard_synthetic_employee();

create or replace function app.create_employee_execution_resource() returns trigger
language plpgsql security definer set search_path = pg_catalog, app as $$
begin
  insert into app.execution_resources(id,company_id,resource_kind,employee_id,display_label)
  values(new.id,new.company_id,'human',new.id,
    coalesce(new.display_name,'Employee ' || left(new.id::text,8))) on conflict do nothing;
  return new;
end $$;

create table app.demo_workspace_policies (
  company_id uuid primary key references app.companies(id),
  enabled boolean not null default false,
  scenario_key text not null check (length(scenario_key) between 1 and 80),
  scenario_version integer not null check (scenario_version > 0),
  allowed_bootstrap_roles text[] not null default array['manager','member']::text[]
    check (allowed_bootstrap_roles <@ array['manager','member']::text[]),
  created_at timestamptz not null default clock_timestamp()
);
-- A bootstrap request intentionally has no client-supplied company selector.
create unique index one_open_demo_workspace on app.demo_workspace_policies ((enabled)) where enabled;

create table app.demo_runs (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id),
  owner_membership_id uuid not null,
  parent_run_id uuid,
  scenario_key text not null,
  scenario_version integer not null check (scenario_version > 0),
  mode text not null check (mode in ('live','authored_replay','authored_d0_check')),
  state text not null default 'active' check (state in ('active','archived')),
  protected boolean not null default false,
  planning_revision bigint not null default 0 check (planning_revision >= 0),
  clock_at timestamptz not null default '2026-09-28 09:00:00 America/Los_Angeles',
  clock_version bigint not null default 1 check (clock_version > 0),
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  archived_at timestamptz,
  unique(company_id,id), unique(company_id,owner_membership_id,idempotency_key),
  foreign key(company_id,owner_membership_id) references app.company_memberships(company_id,id),
  foreign key(company_id,parent_run_id) references app.demo_runs(company_id,id),
  check (id <> company_id), check ((state = 'archived') = (archived_at is not null))
);
create table app.demo_run_memberships (
  company_id uuid not null,
  run_id uuid not null,
  membership_id uuid not null,
  run_role text not null check(run_role in ('owner','operator','participant','viewer')),
  joined_at timestamptz not null default clock_timestamp(),
  revoked_at timestamptz,
  primary key(company_id,run_id,membership_id),
  foreign key(company_id,run_id) references app.demo_runs(company_id,id),
  foreign key(company_id,membership_id) references app.company_memberships(company_id,id)
);
create table app.demo_actor_sessions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  run_id uuid not null,
  performed_by_auth_user_id uuid not null references auth.users(id),
  simulated_actor_employee_id uuid not null,
  created_at timestamptz not null default clock_timestamp(),
  expires_at timestamptz not null default (clock_timestamp() + interval '2 hours'),
  revoked_at timestamptz,
  unique(company_id,id),
  foreign key(company_id,run_id) references app.demo_runs(company_id,id),
  foreign key(company_id,simulated_actor_employee_id) references app.employee_profiles(company_id,id),
  check(expires_at > created_at)
);
create table app.workspace_preferences (
  company_id uuid not null,
  membership_id uuid not null,
  sidebar_mode text not null default 'expanded' check(sidebar_mode in ('expanded','icons')),
  graph_motion boolean not null default true,
  reduce_motion boolean not null default false,
  overlay_enabled boolean not null default false,
  shortcut text not null default 'Control+Space' check(length(shortcut) between 1 and 80),
  notification_preferences jsonb not null default '{}' check(jsonb_typeof(notification_preferences)='object'),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check(row_version > 0),
  primary key(company_id,membership_id),
  foreign key(company_id,membership_id) references app.company_memberships(company_id,id)
);
create table app.demo_bootstrap_events (
  user_id uuid not null references auth.users(id),
  company_id uuid not null,
  membership_id uuid not null,
  requested_role text not null check(requested_role in ('manager','member')),
  idempotency_key text not null check(length(idempotency_key) between 16 and 128),
  created_at timestamptz not null default clock_timestamp(),
  primary key(user_id,idempotency_key),
  foreign key(company_id,membership_id) references app.company_memberships(company_id,id)
);

create function app.current_demo_run_id() returns uuid language sql stable
set search_path=pg_catalog as $$ select nullif(current_setting('app.demo_run_id',true),'')::uuid $$;
create function app.current_scope_id() returns uuid language sql stable
set search_path=pg_catalog,app as $$ select coalesce(app.current_demo_run_id(),app.current_company_id()) $$;
create function app.can_access_demo_run(p_company_id uuid,p_run_id uuid,p_user_id uuid,p_write boolean default false)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
  select exists(select 1 from app.demo_runs r
    join app.demo_run_memberships rm on rm.company_id=r.company_id and rm.run_id=r.id and rm.revoked_at is null
    join app.company_memberships m on m.company_id=rm.company_id and m.id=rm.membership_id
    where r.company_id=p_company_id and r.id=p_run_id and m.user_id=p_user_id
      and m.membership_status='active' and app.has_active_membership(p_company_id,p_user_id)
      and (not p_write or (r.state='active' and rm.run_role in ('owner','operator','participant'))))
$$;
create function app.scope_access(p_company_id uuid,p_run_id uuid,p_write boolean default false)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
  select app.request_context_present() and p_company_id=app.current_company_id()
    and p_run_id is not distinct from app.current_demo_run_id()
    and case when p_run_id is null then app.has_active_membership(p_company_id,app.current_actor_id())
      else app.can_access_demo_run(p_company_id,p_run_id,app.current_actor_id(),p_write) end
$$;
create function app.authorised_demo_actor(p_company_id uuid,p_run_id uuid,p_user_id uuid)
returns uuid language sql stable security definer set search_path=pg_catalog,app as $$
  select s.simulated_actor_employee_id from app.demo_actor_sessions s
    join app.employee_profiles e on e.company_id=s.company_id and e.id=s.simulated_actor_employee_id
    where s.id=nullif(current_setting('app.demo_actor_session_id',true),'')::uuid
      and s.company_id=p_company_id and s.run_id=p_run_id
      and s.performed_by_auth_user_id=p_user_id and p_user_id=app.current_actor_id()
      and s.revoked_at is null and s.expires_at>statement_timestamp()
      and e.profile_kind='synthetic' and e.status='active'
      and app.can_access_demo_run(p_company_id,p_run_id,p_user_id,true)
$$;
create function app.effective_employee_id(p_company_id uuid,p_user_id uuid)
returns uuid language sql stable security definer set search_path=pg_catalog,app as $$
  select case when app.current_demo_run_id() is null then app.employee_id_for_actor(p_company_id,p_user_id)
    else app.authorised_demo_actor(p_company_id,app.current_demo_run_id(),p_user_id) end
$$;

create function app.bootstrap_demo_membership(p_display_name text,p_requested_role text,p_idempotency_key text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,app as $$
declare v_policy app.demo_workspace_policies%rowtype; v_member app.company_memberships%rowtype; v_role text;
begin
  if app.current_actor_id() is null or length(btrim(p_display_name)) not between 1 and 120
    or length(p_idempotency_key) not between 16 and 128 then
    raise exception using errcode='22023',message='invalid_onboarding_request'; end if;
  v_role := case lower(p_requested_role) when 'employee' then 'member' else lower(p_requested_role) end;
  select p.* into v_policy from app.demo_workspace_policies p join app.companies c on c.id=p.company_id
    where p.enabled and c.is_demo and c.status='active';
  if not found or not (v_role=any(v_policy.allowed_bootstrap_roles)) then
    raise exception using errcode='42501',message='demo_onboarding_unavailable'; end if;
  perform pg_advisory_xact_lock(hashtextextended(app.current_actor_id()::text,0));
  select * into v_member from app.company_memberships
    where company_id=v_policy.company_id and user_id=app.current_actor_id();
  if found and (v_member.administrative_role<>v_role or v_member.membership_status<>'active') then
    raise exception using errcode='42501',message='existing_membership_cannot_be_changed'; end if;
  if v_member.id is null then
    insert into app.user_profiles(user_id,display_name) values(app.current_actor_id(),btrim(p_display_name))
      on conflict(user_id) do nothing;
    insert into app.company_memberships(company_id,user_id,administrative_role,joined_at)
      values(v_policy.company_id,app.current_actor_id(),v_role,clock_timestamp()) returning * into v_member;
    insert into app.employee_profiles(company_id,membership_id,display_name)
      values(v_member.company_id,v_member.id,btrim(p_display_name));
  end if;
  insert into app.demo_bootstrap_events(user_id,company_id,membership_id,requested_role,idempotency_key)
    values(app.current_actor_id(),v_member.company_id,v_member.id,v_role,p_idempotency_key)
    on conflict(user_id,idempotency_key) do nothing;
  return jsonb_build_object('company_id',v_member.company_id,'membership_id',v_member.id,
    'role',v_member.administrative_role);
end $$;

create function app.fork_demo_run(p_company_id uuid,p_mode text,p_parent_run_id uuid,p_idempotency_key text)
returns uuid language plpgsql security definer set search_path=pg_catalog,app as $$
declare v_member uuid; v_id uuid; v_policy app.demo_workspace_policies%rowtype; v_existing app.demo_runs%rowtype;
begin
  if p_company_id<>app.current_company_id() or not app.has_active_membership(p_company_id,app.current_actor_id()) then
    raise exception using errcode='42501',message='demo_run_access_denied'; end if;
  select id into v_member from app.company_memberships where company_id=p_company_id and user_id=app.current_actor_id();
  select * into v_policy from app.demo_workspace_policies where company_id=p_company_id and enabled;
  if not found then raise exception using errcode='42501',message='demo_runs_disabled'; end if;
  if p_parent_run_id is not null and not app.can_access_demo_run(p_company_id,p_parent_run_id,app.current_actor_id()) then
    raise exception using errcode='42501',message='demo_run_access_denied'; end if;
  perform pg_advisory_xact_lock(hashtextextended(v_member::text||p_idempotency_key,0));
  select * into v_existing from app.demo_runs where company_id=p_company_id
    and owner_membership_id=v_member and idempotency_key=p_idempotency_key;
  if found then
    if v_existing.mode<>p_mode or v_existing.parent_run_id is distinct from p_parent_run_id then
      raise exception using errcode='23505',message='idempotency_key_reused'; end if;
    return v_existing.id;
  end if;
  insert into app.demo_runs(company_id,owner_membership_id,parent_run_id,scenario_key,scenario_version,mode,idempotency_key)
    values(p_company_id,v_member,p_parent_run_id,v_policy.scenario_key,v_policy.scenario_version,p_mode,p_idempotency_key)
    returning id into v_id;
  insert into app.demo_run_memberships(company_id,run_id,membership_id,run_role) values(p_company_id,v_id,v_member,'owner');
  return v_id;
end $$;
create function app.select_demo_actor(p_company_id uuid,p_run_id uuid,p_employee_id uuid)
returns uuid language plpgsql security definer set search_path=pg_catalog,app as $$
declare v_id uuid;
begin
  if p_company_id<>app.current_company_id() or not app.can_access_demo_run(p_company_id,p_run_id,app.current_actor_id(),true)
    or not exists(select 1 from app.employee_profiles where company_id=p_company_id and id=p_employee_id
      and profile_kind='synthetic' and status='active') then
    raise exception using errcode='42501',message='demo_actor_access_denied'; end if;
  update app.demo_actor_sessions set revoked_at=clock_timestamp() where company_id=p_company_id and run_id=p_run_id
    and performed_by_auth_user_id=app.current_actor_id() and revoked_at is null;
  insert into app.demo_actor_sessions(company_id,run_id,performed_by_auth_user_id,simulated_actor_employee_id)
    values(p_company_id,p_run_id,app.current_actor_id(),p_employee_id) returning id into v_id;
  return v_id;
end $$;
create function app.end_demo_actor_session(p_company_id uuid,p_session_id uuid)
returns void language sql security definer set search_path=pg_catalog,app as $$
  update app.demo_actor_sessions set revoked_at=clock_timestamp()
    where company_id=p_company_id and company_id=app.current_company_id() and id=p_session_id
      and performed_by_auth_user_id=app.current_actor_id() and revoked_at is null
$$;

alter table app.demo_workspace_policies enable row level security;
alter table app.demo_runs enable row level security;
alter table app.demo_run_memberships enable row level security;
alter table app.demo_actor_sessions enable row level security;
alter table app.workspace_preferences enable row level security;
alter table app.demo_bootstrap_events enable row level security;
create policy demo_policy_read on app.demo_workspace_policies for select to coordination_api,coordination_worker
  using(company_id=app.current_company_id() and app.has_active_membership(company_id,app.current_actor_id()));
create policy demo_run_read on app.demo_runs for select to coordination_api,coordination_worker
  using(company_id=app.current_company_id() and app.can_access_demo_run(company_id,id,app.current_actor_id()));
create policy demo_run_member_read on app.demo_run_memberships for select to coordination_api,coordination_worker
  using(company_id=app.current_company_id() and app.can_access_demo_run(company_id,run_id,app.current_actor_id()));
create policy demo_actor_self_read on app.demo_actor_sessions for select to coordination_api,coordination_worker
  using(company_id=app.current_company_id() and performed_by_auth_user_id=app.current_actor_id()
    and app.can_access_demo_run(company_id,run_id,app.current_actor_id()));
create policy workspace_preferences_self on app.workspace_preferences for all to coordination_api
  using(company_id=app.current_company_id() and exists(select 1 from app.company_memberships m
    where m.company_id=workspace_preferences.company_id and m.id=membership_id and m.user_id=app.current_actor_id()))
  with check(company_id=app.current_company_id() and exists(select 1 from app.company_memberships m
    where m.company_id=workspace_preferences.company_id and m.id=membership_id and m.user_id=app.current_actor_id()));
grant select on app.demo_workspace_policies,app.demo_runs,app.demo_run_memberships,app.demo_actor_sessions
  to coordination_api,coordination_worker;
grant select,insert,update on app.workspace_preferences to coordination_api;
create trigger workspace_preferences_touch before update on app.workspace_preferences
  for each row execute function app.touch_updated_row();
create trigger demo_runs_touch before update on app.demo_runs for each row execute function app.touch_updated_row();

revoke all on function app.guard_synthetic_employee(),app.current_demo_run_id(),app.current_scope_id(),
  app.can_access_demo_run(uuid,uuid,uuid,boolean),app.scope_access(uuid,uuid,boolean),
  app.authorised_demo_actor(uuid,uuid,uuid),app.effective_employee_id(uuid,uuid),
  app.bootstrap_demo_membership(text,text,text),app.fork_demo_run(uuid,text,uuid,text),
  app.select_demo_actor(uuid,uuid,uuid),app.end_demo_actor_session(uuid,uuid) from public;
grant execute on function app.current_demo_run_id(),app.current_scope_id(),
  app.can_access_demo_run(uuid,uuid,uuid,boolean),app.scope_access(uuid,uuid,boolean),
  app.authorised_demo_actor(uuid,uuid,uuid),app.effective_employee_id(uuid,uuid) to coordination_api,coordination_worker;
grant execute on function app.bootstrap_demo_membership(text,text,text),app.fork_demo_run(uuid,text,uuid,text),
  app.select_demo_actor(uuid,uuid,uuid),app.end_demo_actor_session(uuid,uuid) to coordination_api;

insert into app_private.migration_contract(version,name) values ('20260927010000','alto_demo_identity_runs');
