-- Source/version/access records and private object registry.

create table app.source_records (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  owning_team_id uuid null,
  uploaded_by_employee_id uuid null,
  source_kind text not null check (source_kind in ('upload', 'calendar', 'document', 'fixture')),
  title text null check (title is null or length(title) <= 240),
  classification text not null default 'internal'
    check (classification in ('internal', 'confidential', 'restricted')),
  authority_status text not null default 'unverified'
    check (authority_status in ('unverified', 'authoritative', 'superseded', 'revoked')),
  access_policy jsonb not null default '{}'::jsonb check (jsonb_typeof(access_policy) = 'object'),
  current_version_id uuid null,
  status text not null default 'active' check (status in ('active', 'deleted', 'revoked')),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  foreign key (company_id, owning_team_id) references app.teams(company_id, id),
  foreign key (company_id, uploaded_by_employee_id)
    references app.employee_profiles(company_id, id)
);

create table app.source_versions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  source_id uuid not null,
  provider_version text null,
  content_sha256 bytea not null check (octet_length(content_sha256) = 32),
  retrieved_at timestamptz not null,
  blob_bucket_id text null,
  blob_object_path text null,
  extraction_version text null,
  access_snapshot jsonb not null check (jsonb_typeof(access_snapshot) = 'object'),
  expires_at timestamptz null,
  created_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  foreign key (company_id, source_id)
    references app.source_records(company_id, id) on delete cascade,
  check ((blob_bucket_id is null) = (blob_object_path is null))
);

alter table app.source_records
  add constraint source_records_current_version_fk
  foreign key (company_id, current_version_id)
  references app.source_versions(company_id, id);

create table app.source_access_grants (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  source_id uuid not null,
  principal_kind text not null check (principal_kind in ('company', 'team', 'employee')),
  team_id uuid null,
  employee_id uuid null,
  access_type text not null check (access_type in ('read', 'cite', 'manage')),
  authority_reference text not null check (length(authority_reference) between 1 and 240),
  expires_at timestamptz null,
  revoked_at timestamptz null,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  foreign key (company_id, source_id)
    references app.source_records(company_id, id) on delete cascade,
  foreign key (company_id, team_id) references app.teams(company_id, id),
  foreign key (company_id, employee_id)
    references app.employee_profiles(company_id, id),
  check (
    (principal_kind = 'company' and team_id is null and employee_id is null)
    or (principal_kind = 'team' and team_id is not null and employee_id is null)
    or (principal_kind = 'employee' and team_id is null and employee_id is not null)
  )
);

create table app.private_files (
  id uuid primary key,
  company_id uuid not null references app.companies(id) on delete cascade,
  bucket_id text not null check (bucket_id in ('coordination-quarantine', 'coordination-private')),
  object_path text not null,
  purpose text not null check (purpose in ('source', 'submission', 'evidence')),
  source_id uuid null,
  uploader_employee_id uuid not null,
  display_filename text not null check (length(display_filename) between 1 and 240),
  declared_mime_type text not null,
  detected_mime_type text null,
  size_bytes bigint not null check (size_bytes between 1 and 26214400),
  content_sha256 bytea null check (content_sha256 is null or octet_length(content_sha256) = 32),
  state text not null default 'pending_upload'
    check (state in ('pending_upload', 'quarantined', 'available', 'rejected', 'deleted')),
  upload_intent_expires_at timestamptz not null,
  uploaded_at timestamptz null,
  scanned_at timestamptz null,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  unique (bucket_id, object_path),
  foreign key (company_id, source_id)
    references app.source_records(company_id, id),
  foreign key (company_id, uploader_employee_id)
    references app.employee_profiles(company_id, id),
  check (object_path like company_id::text || '/%')
);

create index source_records_company_status on app.source_records (company_id, status);
create index source_versions_source_lookup on app.source_versions (company_id, source_id, retrieved_at desc);
create index source_access_grants_lookup
  on app.source_access_grants (company_id, source_id, principal_kind, revoked_at, expires_at);
create index private_files_company_state on app.private_files (company_id, state);

create or replace function app.can_read_source(
  p_user_id uuid,
  p_company_id uuid,
  p_source_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select app.has_active_membership(p_company_id, p_user_id)
    and exists (
      select 1 from app.source_records as source
      where source.company_id = p_company_id
        and source.id = p_source_id
        and source.status = 'active'
    )
    and (
      app.is_company_admin(p_company_id, p_user_id)
      or exists (
        select 1
        from app.source_access_grants as access
        where access.company_id = p_company_id
          and access.source_id = p_source_id
          and access.revoked_at is null
          and (access.expires_at is null or access.expires_at > statement_timestamp())
          and (
            access.principal_kind = 'company'
            or (
              access.principal_kind = 'employee'
              and exists (
                select 1
                from app.employee_profiles as employee
                join app.company_memberships as membership
                  on membership.company_id = employee.company_id
                 and membership.id = employee.membership_id
                where employee.company_id = p_company_id
                  and employee.id = access.employee_id
                  and membership.user_id = p_user_id
                  and membership.membership_status = 'active'
              )
            )
            or (
              access.principal_kind = 'team'
              and exists (
                select 1
                from app.team_memberships as team_member
                join app.employee_profiles as employee
                  on employee.company_id = team_member.company_id
                 and employee.id = team_member.employee_id
                join app.company_memberships as membership
                  on membership.company_id = employee.company_id
                 and membership.id = employee.membership_id
                where team_member.company_id = p_company_id
                  and team_member.team_id = access.team_id
                  and team_member.valid_from <= statement_timestamp()
                  and (team_member.valid_to is null or team_member.valid_to > statement_timestamp())
                  and membership.user_id = p_user_id
                  and membership.membership_status = 'active'
              )
            )
          )
      )
    )
$$;

create or replace function app.can_read_private_file(
  p_user_id uuid,
  p_company_id uuid,
  p_file_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1
    from app.private_files as file
    join app.employee_profiles as uploader
      on uploader.company_id = file.company_id
     and uploader.id = file.uploader_employee_id
    join app.company_memberships as uploader_membership
      on uploader_membership.company_id = uploader.company_id
     and uploader_membership.id = uploader.membership_id
    where file.company_id = p_company_id
      and file.id = p_file_id
      and file.state = 'available'
      and app.has_active_membership(p_company_id, p_user_id)
      and (
        app.is_company_admin(p_company_id, p_user_id)
        or uploader_membership.user_id = p_user_id
        or (file.source_id is not null and app.can_read_source(p_user_id, p_company_id, file.source_id))
      )
  )
$$;

revoke execute on function app.can_read_source(uuid, uuid, uuid) from public;
revoke execute on function app.can_read_private_file(uuid, uuid, uuid) from public;
grant execute on function app.can_read_source(uuid, uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.can_read_private_file(uuid, uuid, uuid)
  to coordination_api, coordination_worker;

alter table app.source_records enable row level security;
alter table app.source_versions enable row level security;
alter table app.source_access_grants enable row level security;
alter table app.private_files enable row level security;

create policy source_records_authorized_select on app.source_records
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_source(app.current_actor_id(), company_id, id)
  );

create policy source_versions_authorized_select on app.source_versions
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_source(app.current_actor_id(), company_id, source_id)
  );

create policy source_access_authorized_select on app.source_access_grants
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_source(app.current_actor_id(), company_id, source_id)
  );

create policy private_files_authorized_select on app.private_files
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_private_file(app.current_actor_id(), company_id, id)
  );

grant select on app.source_records, app.source_versions, app.source_access_grants,
  app.private_files to coordination_api, coordination_worker;

create trigger source_records_touch_updated before update on app.source_records
  for each row execute function app.touch_updated_row();
create trigger source_access_grants_touch_updated before update on app.source_access_grants
  for each row execute function app.touch_updated_row();
create trigger private_files_touch_updated before update on app.private_files
  for each row execute function app.touch_updated_row();

insert into app_private.migration_contract (version, name)
values ('20260926012000', 'sources_and_private_storage');
