-- Trusted candidate materialization inputs and durable stage for the connected demo.

alter table app.durable_jobs drop constraint durable_jobs_job_kind_check;
alter table app.durable_jobs add constraint durable_jobs_job_kind_check check (job_kind in (
  'interpretation.run', 'planning.materialize', 'planning.run',
  'private_file.scan', 'outbox.deliver'
));

create table app.planning_resource_profiles (
  company_id uuid not null,
  resource_id uuid not null,
  timezone text not null check (length(btrim(timezone)) between 1 and 64),
  availability_windows jsonb not null check (
    jsonb_typeof(availability_windows) = 'array'
    and jsonb_array_length(availability_windows) between 1 and 500
  ),
  capability_keys jsonb not null default '[]'::jsonb check (
    jsonb_typeof(capability_keys) = 'array'
  ),
  permission_keys jsonb not null default '[]'::jsonb check (
    jsonb_typeof(permission_keys) = 'array'
  ),
  daily_active_minutes integer not null check (daily_active_minutes between 0 and 1440),
  profile_revision bigint not null default 1 check (profile_revision > 0),
  estimate_revision bigint not null default 1 check (estimate_revision > 0),
  active boolean not null default true,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  primary key (company_id, resource_id),
  foreign key (company_id, resource_id)
    references app.execution_resources(company_id, id) on delete cascade
);

create trigger planning_resource_profiles_touch_updated
  before update on app.planning_resource_profiles
  for each row execute function app.touch_updated_row();

alter table app.planning_resource_profiles enable row level security;
alter table app.planning_resource_profiles force row level security;

create policy planning_resource_profiles_worker_select
  on app.planning_resource_profiles for select to coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.has_active_membership(company_id, app.current_actor_id())
  );

revoke all on table app.planning_resource_profiles
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;
grant select on table app.planning_resource_profiles to coordination_worker;

create or replace function app.enqueue_candidate_materialization_job()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_requester uuid;
begin
  if new.admission_status <> 'admitted' then
    return new;
  end if;
  select requester_membership_id into v_requester
  from app.planning_requests
  where company_id = new.company_id and id = new.request_id;
  insert into app.durable_jobs (
    company_id, job_kind, aggregate_id, payload, requested_by_membership_id,
    idempotency_key, command_digest, correlation_id
  ) values (
    new.company_id, 'planning.materialize', new.id,
    jsonb_build_object('candidate_contract_id', new.id), v_requester,
    'planning.materialize:' || new.id::text,
    extensions.digest(convert_to(new.id::text || ':'
      || encode(new.contract_digest, 'hex'), 'UTF8'), 'sha256'),
    gen_random_uuid()
  ) on conflict (company_id, job_kind, aggregate_id) do nothing;
  return new;
end
$$;

create trigger candidate_contracts_enqueue_materialization
  after insert on app.candidate_contracts
  for each row execute function app.enqueue_candidate_materialization_job();

insert into app.durable_jobs (
  company_id, job_kind, aggregate_id, payload, requested_by_membership_id,
  idempotency_key, command_digest, correlation_id
)
select candidate.company_id, 'planning.materialize', candidate.id,
  jsonb_build_object('candidate_contract_id', candidate.id),
  request.requester_membership_id,
  'planning.materialize:' || candidate.id::text,
  extensions.digest(convert_to(candidate.id::text || ':'
    || encode(candidate.contract_digest, 'hex'), 'UTF8'), 'sha256'),
  gen_random_uuid()
from app.candidate_contracts as candidate
join app.planning_requests as request
  on request.company_id = candidate.company_id and request.id = candidate.request_id
where candidate.admission_status = 'admitted'
  and not exists (
    select 1 from app.planning_snapshots as snapshot
    where snapshot.company_id = candidate.company_id
      and snapshot.candidate_contract_id = candidate.id
  )
on conflict (company_id, job_kind, aggregate_id) do nothing;

create or replace function app.reconcile_unauthorised_durable_jobs()
returns integer
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_count integer;
begin
  with invalid_jobs as (
    select job.company_id, job.id
    from app.durable_jobs as job
    left join app.company_memberships as membership
      on membership.company_id = job.company_id
     and membership.id = job.requested_by_membership_id
     and membership.membership_status = 'active'
     and membership.administrative_role in ('manager', 'company_admin')
    where job.state in ('queued', 'retry_scheduled')
      and job.job_kind in ('interpretation.run', 'planning.materialize', 'planning.run')
      and membership.id is null
    for update of job skip locked
  )
  update app.durable_jobs as job
  set state = 'review_required',
      last_error_code = 'requester_authority_revoked',
      last_error_message = null,
      completed_at = clock_timestamp(),
      row_version = job.row_version + 1
  from invalid_jobs
  where job.company_id = invalid_jobs.company_id and job.id = invalid_jobs.id;
  get diagnostics v_count = row_count;
  return v_count;
end
$$;

revoke execute on function app.enqueue_candidate_materialization_job() from public;

create or replace function app.create_default_committed_task_review_policy()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_requester_membership_id uuid;
  v_reviewer_employee_id uuid;
begin
  select request.requester_membership_id, employee.id
  into v_requester_membership_id, v_reviewer_employee_id
  from app.planning_requests as request
  join app.employee_profiles as employee
    on employee.company_id = request.company_id
   and employee.membership_id = request.requester_membership_id
   and employee.status = 'active'
  where request.company_id = new.company_id and request.id = new.source_request_id;

  if v_reviewer_employee_id is null
     or v_reviewer_employee_id = new.owner_resource_id then
    return new;
  end if;

  insert into app.task_review_policies (
    company_id, task_id, version, reviewer_employee_id, self_certifiable,
    self_certification_rule, assigned_by_membership_id, idempotency_key,
    command_digest, correlation_id, resulting_task_version, active
  ) values (
    new.company_id, new.task_id, 1, v_reviewer_employee_id, false, null,
    v_requester_membership_id, 'commit-review:' || new.task_id::text,
    extensions.digest(convert_to(new.task_id::text || ':'
      || v_reviewer_employee_id::text, 'UTF8'), 'sha256'),
    gen_random_uuid(), new.row_version, true
  ) on conflict (company_id, task_id, version) do nothing;
  return new;
end
$$;

create trigger work_items_create_default_review_policy
  after insert on app.work_items
  for each row execute function app.create_default_committed_task_review_policy();

revoke execute on function app.create_default_committed_task_review_policy() from public;

insert into app_private.migration_contract (version, name)
values ('20260926019000', 'connected_demo_materialization');
