-- Narrow Storage ticket functions, private buckets and demo-only reset protection.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  (
    'coordination-quarantine',
    'coordination-quarantine',
    false,
    26214400,
    array[
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'text/csv',
      'text/plain'
    ]
  ),
  (
    'coordination-private',
    'coordination-private',
    false,
    26214400,
    array[
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'text/csv',
      'text/plain'
    ]
  )
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

create or replace function app.issue_private_storage_ticket(
  p_action text,
  p_company_id uuid,
  p_file_id uuid,
  p_object_path text default null,
  p_purpose text default null,
  p_source_id uuid default null,
  p_display_filename text default null,
  p_content_type text default null,
  p_size_bytes bigint default null
)
returns table (file_id uuid, bucket_id text, object_path text, file_state text)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_user_id uuid := auth.uid();
  v_employee_id uuid;
begin
  if v_user_id is null or not app.has_active_membership(p_company_id, v_user_id) then
    return;
  end if;

  select employee.id
  into v_employee_id
  from app.employee_profiles as employee
  join app.company_memberships as membership
    on membership.company_id = employee.company_id
   and membership.id = employee.membership_id
  where employee.company_id = p_company_id
    and employee.status = 'active'
    and membership.user_id = v_user_id
    and membership.membership_status = 'active';

  if v_employee_id is null then
    return;
  end if;

  if p_action = 'create-upload' then
    if p_object_path is null
      or p_object_path not like p_company_id::text || '/' || p_file_id::text || '/%'
      or p_purpose is null
      or p_purpose not in ('source', 'submission', 'evidence')
      or p_display_filename is null
      or length(p_display_filename) not between 1 and 240
      or p_content_type is null
      or p_content_type not in (
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/csv',
        'text/plain'
      )
      or p_size_bytes is null
      or p_size_bytes not between 1 and 26214400
      or (
        p_source_id is not null
        and not app.can_read_source(v_user_id, p_company_id, p_source_id)
      ) then
      return;
    end if;

    insert into app.private_files (
      id,
      company_id,
      bucket_id,
      object_path,
      purpose,
      source_id,
      uploader_employee_id,
      display_filename,
      declared_mime_type,
      size_bytes,
      upload_intent_expires_at
    ) values (
      p_file_id,
      p_company_id,
      'coordination-quarantine',
      p_object_path,
      p_purpose,
      p_source_id,
      v_employee_id,
      p_display_filename,
      p_content_type,
      p_size_bytes,
      statement_timestamp() + interval '10 minutes'
    );

    return query
      select file.id, file.bucket_id, file.object_path, file.state
      from app.private_files as file
      where file.company_id = p_company_id and file.id = p_file_id;
    return;
  end if;

  if p_action = 'create-download' then
    return query
      select file.id, file.bucket_id, file.object_path, file.state
      from app.private_files as file
      where file.company_id = p_company_id
        and file.id = p_file_id
        and app.can_read_private_file(v_user_id, p_company_id, file.id);
    return;
  end if;

  return;
end
$$;

create or replace function app.finalize_private_upload(
  p_company_id uuid,
  p_file_id uuid,
  p_detected_mime_type text,
  p_observed_size_bytes bigint
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_user_id uuid := auth.uid();
  v_updated integer;
begin
  if v_user_id is null or not app.has_active_membership(p_company_id, v_user_id) then
    return false;
  end if;

  update app.private_files as file
  set state = 'quarantined',
      detected_mime_type = p_detected_mime_type,
      size_bytes = p_observed_size_bytes,
      uploaded_at = statement_timestamp()
  from app.employee_profiles as employee
  join app.company_memberships as membership
    on membership.company_id = employee.company_id
   and membership.id = employee.membership_id
  where file.company_id = p_company_id
    and file.id = p_file_id
    and file.uploader_employee_id = employee.id
    and membership.user_id = v_user_id
    and membership.membership_status = 'active'
    and file.state = 'pending_upload'
    and file.upload_intent_expires_at > statement_timestamp()
    and p_observed_size_bytes is not null
    and p_observed_size_bytes between 1 and 26214400
    and p_observed_size_bytes <= file.size_bytes
    and p_detected_mime_type is not null
    and p_detected_mime_type = file.declared_mime_type;

  get diagnostics v_updated = row_count;
  return v_updated = 1;
end
$$;

revoke execute on function app.issue_private_storage_ticket(
  text, uuid, uuid, text, text, uuid, text, text, bigint
) from public;
revoke execute on function app.finalize_private_upload(uuid, uuid, text, bigint) from public;
grant usage on schema app to authenticated;
grant execute on function app.issue_private_storage_ticket(
  text, uuid, uuid, text, text, uuid, text, text, bigint
) to authenticated;
grant execute on function app.finalize_private_upload(uuid, uuid, text, bigint) to authenticated;

-- No authenticated CRUD policy is created for the application buckets. Users receive
-- time-bounded signed operations only after the ticket functions re-authorise current access.

create or replace function app_private.reset_demo_company(p_company_id uuid)
returns void
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  if not exists (
    select 1 from app.companies where id = p_company_id and is_demo is true
  ) then
    raise exception 'demo reset refused for non-demo or unknown company'
      using errcode = '42501';
  end if;

  delete from app.private_files where company_id = p_company_id;
  delete from app.source_access_grants where company_id = p_company_id;
  update app.source_records set current_version_id = null where company_id = p_company_id;
  delete from app.source_versions where company_id = p_company_id;
  delete from app.source_records where company_id = p_company_id;
  delete from app.invitations where company_id = p_company_id;
  delete from app.team_memberships where company_id = p_company_id;
  delete from app.teams where company_id = p_company_id;
  delete from app.employee_profiles where company_id = p_company_id;
  delete from app.company_memberships where company_id = p_company_id;
  update app.companies
  set planning_revision = 0, policy_revision = 0
  where id = p_company_id;
end
$$;

revoke execute on function app_private.reset_demo_company(uuid) from public, anon,
  authenticated, service_role, coordination_api, coordination_worker;

insert into app_private.migration_contract (version, name)
values ('20260926013000', 'storage_gateway_and_demo_guard');
