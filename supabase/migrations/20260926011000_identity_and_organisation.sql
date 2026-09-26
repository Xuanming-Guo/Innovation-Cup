-- Company identity, membership and organisation records.

create table app.companies (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique check (slug = lower(slug) and slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  name text not null check (length(btrim(name)) between 1 and 160),
  default_timezone text not null default 'UTC',
  default_locale text not null default 'en-GB',
  status text not null default 'active' check (status in ('active', 'suspended', 'closed')),
  is_demo boolean not null default false,
  planning_revision bigint not null default 0 check (planning_revision >= 0),
  policy_revision bigint not null default 0 check (policy_revision >= 0),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (id, is_demo)
);

create table app.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (length(btrim(display_name)) between 1 and 120),
  ui_locale text not null default 'en-GB',
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0)
);

create table app.company_memberships (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  membership_status text not null default 'active'
    check (membership_status in ('invited', 'active', 'suspended', 'revoked')),
  administrative_role text not null default 'member'
    check (administrative_role in ('member', 'manager', 'company_admin')),
  joined_at timestamptz null,
  suspended_at timestamptz null,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  unique (company_id, user_id),
  check ((membership_status = 'suspended') = (suspended_at is not null)),
  check (membership_status <> 'active' or joined_at is not null)
);

create table app.teams (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  name text not null check (length(btrim(name)) between 1 and 120),
  description text null check (description is null or length(description) <= 2000),
  status text not null default 'active' check (status in ('active', 'archived')),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  unique (company_id, name)
);

create table app.employee_profiles (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  membership_id uuid not null,
  timezone text not null default 'UTC',
  preferred_locale text not null default 'en-GB',
  status text not null default 'active' check (status in ('active', 'inactive')),
  profile_revision bigint not null default 1 check (profile_revision > 0),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  unique (company_id, membership_id),
  foreign key (company_id, membership_id)
    references app.company_memberships(company_id, id) on delete cascade
);

create table app.team_memberships (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  team_id uuid not null,
  employee_id uuid not null,
  team_role text not null default 'contributor'
    check (team_role in ('contributor', 'reviewer', 'manager')),
  assignment_eligible boolean not null default true,
  valid_from timestamptz not null default clock_timestamp(),
  valid_to timestamptz null,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  unique (company_id, team_id, employee_id, valid_from),
  foreign key (company_id, team_id) references app.teams(company_id, id) on delete cascade,
  foreign key (company_id, employee_id)
    references app.employee_profiles(company_id, id) on delete cascade,
  check (valid_to is null or valid_to > valid_from)
);

create unique index team_memberships_one_open_interval
  on app.team_memberships (company_id, team_id, employee_id)
  where valid_to is null;

create table app.invitations (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  intended_email text not null check (intended_email = lower(btrim(intended_email))),
  token_hash bytea not null unique check (octet_length(token_hash) = 32),
  proposed_administrative_role text not null default 'member'
    check (proposed_administrative_role in ('member', 'manager', 'company_admin')),
  proposed_team_id uuid null,
  proposed_team_role text null
    check (proposed_team_role is null or proposed_team_role in ('contributor', 'reviewer', 'manager')),
  invited_by_membership_id uuid not null,
  expires_at timestamptz not null,
  accepted_at timestamptz null,
  revoked_at timestamptz null,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  foreign key (company_id, proposed_team_id) references app.teams(company_id, id),
  foreign key (company_id, invited_by_membership_id)
    references app.company_memberships(company_id, id),
  check (not (accepted_at is not null and revoked_at is not null)),
  check (expires_at > created_at)
);

create index company_memberships_user_lookup
  on app.company_memberships (user_id, company_id, membership_status);
create index employee_profiles_membership_lookup
  on app.employee_profiles (company_id, membership_id, status);
create index team_memberships_employee_lookup
  on app.team_memberships (company_id, employee_id, valid_to);

create or replace function app.has_active_membership(p_company_id uuid, p_user_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1
    from app.company_memberships as membership
    join app.companies as company on company.id = membership.company_id
    where membership.company_id = p_company_id
      and membership.user_id = p_user_id
      and membership.membership_status = 'active'
      and company.status = 'active'
  )
$$;

create or replace function app.is_company_admin(p_company_id uuid, p_user_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1
    from app.company_memberships
    where company_id = p_company_id
      and user_id = p_user_id
      and membership_status = 'active'
      and administrative_role = 'company_admin'
  )
$$;

revoke execute on function app.has_active_membership(uuid, uuid) from public;
revoke execute on function app.is_company_admin(uuid, uuid) from public;
grant execute on function app.has_active_membership(uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.is_company_admin(uuid, uuid)
  to coordination_api, coordination_worker;

alter table app.companies enable row level security;
alter table app.user_profiles enable row level security;
alter table app.company_memberships enable row level security;
alter table app.teams enable row level security;
alter table app.employee_profiles enable row level security;
alter table app.team_memberships enable row level security;
alter table app.invitations enable row level security;

create policy companies_current_tenant_select on app.companies
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and id = app.current_company_id()
    and app.has_active_membership(id, app.current_actor_id())
  );

create policy user_profiles_self_select on app.user_profiles
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and user_id = app.current_actor_id());

create policy memberships_current_tenant_select on app.company_memberships
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.has_active_membership(company_id, app.current_actor_id())
  );

create policy teams_current_tenant_select on app.teams
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.has_active_membership(company_id, app.current_actor_id())
  );

create policy employees_current_tenant_select on app.employee_profiles
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.has_active_membership(company_id, app.current_actor_id())
  );

create policy team_memberships_current_tenant_select on app.team_memberships
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.has_active_membership(company_id, app.current_actor_id())
  );

create policy invitations_company_admin_select on app.invitations
  for select to coordination_api
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.is_company_admin(company_id, app.current_actor_id())
  );

grant select on app.companies, app.user_profiles, app.company_memberships,
  app.teams, app.employee_profiles, app.team_memberships, app.invitations
  to coordination_api, coordination_worker;

create trigger companies_touch_updated before update on app.companies
  for each row execute function app.touch_updated_row();
create trigger user_profiles_touch_updated before update on app.user_profiles
  for each row execute function app.touch_updated_row();
create trigger company_memberships_touch_updated before update on app.company_memberships
  for each row execute function app.touch_updated_row();
create trigger teams_touch_updated before update on app.teams
  for each row execute function app.touch_updated_row();
create trigger employee_profiles_touch_updated before update on app.employee_profiles
  for each row execute function app.touch_updated_row();
create trigger team_memberships_touch_updated before update on app.team_memberships
  for each row execute function app.touch_updated_row();
create trigger invitations_touch_updated before update on app.invitations
  for each row execute function app.touch_updated_row();

insert into app_private.migration_contract (version, name)
values ('20260926011000', 'identity_and_organisation');
