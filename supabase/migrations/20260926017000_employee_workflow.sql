-- Authorised employee task lifecycle, private submissions and accountable review.

create table app.execution_resources (
  id uuid primary key,
  company_id uuid not null references app.companies(id) on delete cascade,
  resource_kind text not null check (resource_kind in ('human', 'shared', 'unresolved')),
  employee_id uuid null,
  display_label text not null check (length(btrim(display_label)) between 1 and 120),
  status text not null default 'active' check (status in ('active', 'inactive')),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  foreign key (company_id, employee_id)
    references app.employee_profiles(company_id, id),
  check ((resource_kind = 'human') = (employee_id is not null)),
  check (resource_kind <> 'unresolved' or status = 'inactive')
);

create unique index execution_resources_one_per_employee
  on app.execution_resources (company_id, employee_id)
  where employee_id is not null;

insert into app.execution_resources (id, company_id, resource_kind, employee_id, display_label)
select employee.id, employee.company_id, 'human', employee.id,
       'Employee ' || left(employee.id::text, 8)
from app.employee_profiles as employee
on conflict do nothing;

insert into app.execution_resources (id, company_id, resource_kind, display_label)
select resource.id, resource.company_id, 'unresolved',
       'Imported resource ' || left(resource.id::text, 8)
from (
  select company_id, owner_resource_id as id from app.work_items
    where owner_resource_id is not null
  union
  select company_id, resource_id as id from app.work_assignments
  union
  select company_id, resource_id as id from app.committed_schedule_blocks
) as resource
where not exists (
  select 1 from app.execution_resources as known
  where known.company_id = resource.company_id and known.id = resource.id
)
on conflict do nothing;

alter table app.work_items add constraint work_items_owner_execution_resource_fkey
  foreign key (company_id, owner_resource_id)
  references app.execution_resources(company_id, id);
alter table app.work_assignments add constraint work_assignments_execution_resource_fkey
  foreign key (company_id, resource_id)
  references app.execution_resources(company_id, id);
alter table app.committed_schedule_blocks
  add constraint committed_schedule_execution_resource_fkey
  foreign key (company_id, resource_id)
  references app.execution_resources(company_id, id);

create or replace function app.create_employee_execution_resource()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  insert into app.execution_resources (
    id, company_id, resource_kind, employee_id, display_label
  ) values (
    new.id, new.company_id, 'human', new.id, 'Employee ' || left(new.id::text, 8)
  ) on conflict do nothing;
  return new;
end
$$;

create trigger employee_profile_execution_resource
  after insert on app.employee_profiles
  for each row execute function app.create_employee_execution_resource();

alter table app.work_items drop constraint work_items_status_check;
update app.work_items as item
set status = case when resource.resource_kind = 'human' then 'assigned' else 'ready' end
from app.execution_resources as resource
where item.status = 'committed' and resource.company_id = item.company_id
  and resource.id = item.owner_resource_id;
update app.work_items set status = 'ready'
where status = 'committed';
alter table app.work_items alter column status set default 'ready';
alter table app.work_items add constraint work_items_status_check check (status in (
  'ready', 'assigned', 'acknowledged', 'in_progress', 'blocked', 'submitted',
  'accepted', 'revision_requested', 'cancelled'
));

create unique index work_assignments_one_active_owner
  on app.work_assignments (company_id, task_id)
  where active and assignment_role = 'owner';

alter table app.work_items add column employee_brief_version_id uuid null;
alter table app.work_items add constraint work_items_employee_brief_version_fkey
  foreign key (company_id, employee_brief_version_id)
  references app.employee_brief_versions(company_id, id);

update app.work_items as item
set employee_brief_version_id = (
  select candidate.id
  from app.employee_brief_versions as candidate
  where candidate.company_id = item.company_id
    and candidate.plan_id = item.source_plan_id
  order by candidate.version desc limit 1
)
where exists (
  select 1 from app.employee_brief_versions as candidate
  where candidate.company_id = item.company_id
    and candidate.plan_id = item.source_plan_id
);

create or replace function app.bind_work_item_execution_context()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_resource_kind text;
begin
  if new.owner_resource_id is not null then
    select resource_kind into v_resource_kind
    from app.execution_resources
    where company_id = new.company_id and id = new.owner_resource_id and status = 'active';
  end if;
  new.status := case when v_resource_kind = 'human' then 'assigned' else 'ready' end;
  select brief.id into new.employee_brief_version_id
  from app.employee_brief_versions as brief
  where brief.company_id = new.company_id and brief.plan_id = new.source_plan_id
  order by brief.version desc limit 1;
  return new;
end
$$;

create trigger work_items_bind_execution_context
  before insert on app.work_items
  for each row execute function app.bind_work_item_execution_context();

create table app.task_review_policies (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  task_id uuid not null,
  version integer not null check (version > 0),
  reviewer_employee_id uuid null,
  self_certifiable boolean not null default false,
  self_certification_rule text null
    check (self_certification_rule is null or length(self_certification_rule) <= 1000),
  assigned_by_membership_id uuid not null,
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  command_digest bytea not null check (octet_length(command_digest) = 32),
  correlation_id uuid not null,
  resulting_task_version bigint not null check (resulting_task_version > 0),
  active boolean not null default true,
  created_at timestamptz not null default clock_timestamp(),
  superseded_at timestamptz null,
  unique (company_id, id),
  unique (company_id, task_id, version),
  unique (company_id, assigned_by_membership_id, idempotency_key),
  foreign key (company_id, task_id) references app.work_items(company_id, task_id),
  foreign key (company_id, reviewer_employee_id)
    references app.employee_profiles(company_id, id),
  foreign key (company_id, assigned_by_membership_id)
    references app.company_memberships(company_id, id),
  check (reviewer_employee_id is not null or self_certifiable),
  check ((not self_certifiable) = (self_certification_rule is null)),
  check ((not active) = (superseded_at is not null))
);

create unique index task_review_policy_one_active
  on app.task_review_policies (company_id, task_id) where active;

create table app.task_access_grants (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  task_id uuid not null,
  employee_id uuid not null,
  access_role text not null check (access_role in ('manager', 'participant')),
  granted_by_membership_id uuid not null,
  active boolean not null default true,
  granted_at timestamptz not null default clock_timestamp(),
  revoked_at timestamptz null,
  unique (company_id, id),
  unique (company_id, task_id, employee_id, access_role),
  foreign key (company_id, task_id) references app.work_items(company_id, task_id),
  foreign key (company_id, employee_id)
    references app.employee_profiles(company_id, id),
  foreign key (company_id, granted_by_membership_id)
    references app.company_memberships(company_id, id),
  check (active = (revoked_at is null))
);

create or replace function app.grant_committed_task_manager_access()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  insert into app.task_access_grants (
    company_id, task_id, employee_id, access_role, granted_by_membership_id
  )
  select new.company_id, new.task_id, employee.id, 'manager', commitment.committed_by_membership_id
  from app.plan_commitments as commitment
  join app.employee_profiles as employee
    on employee.company_id = commitment.company_id
   and employee.membership_id = commitment.committed_by_membership_id
   and employee.status = 'active'
  where commitment.company_id = new.company_id and commitment.plan_id = new.source_plan_id
  union
  select new.company_id, new.task_id, project.manager_employee_id, 'manager',
         commitment.committed_by_membership_id
  from app.projects as project
  join app.plan_commitments as commitment
    on commitment.company_id = new.company_id and commitment.plan_id = new.source_plan_id
  where project.company_id = new.company_id and project.id = new.project_id
  on conflict do nothing;
  return new;
end
$$;

create trigger work_items_grant_manager_access
  after insert on app.work_items
  for each row execute function app.grant_committed_task_manager_access();

create table app.employee_brief_audience_grants (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  brief_version_id uuid not null,
  principal_kind text not null check (principal_kind in ('employee', 'team')),
  employee_id uuid null,
  team_id uuid null,
  granted_at timestamptz not null default clock_timestamp(),
  revoked_at timestamptz null,
  unique (company_id, id),
  unique nulls not distinct (
    company_id, brief_version_id, principal_kind, employee_id, team_id
  ),
  foreign key (company_id, brief_version_id)
    references app.employee_brief_versions(company_id, id) on delete cascade,
  foreign key (company_id, employee_id)
    references app.employee_profiles(company_id, id),
  foreign key (company_id, team_id) references app.teams(company_id, id),
  check (
    (principal_kind = 'employee' and employee_id is not null and team_id is null)
    or (principal_kind = 'team' and employee_id is null and team_id is not null)
  )
);

create or replace function app.materialize_employee_brief_audience()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  if jsonb_typeof(coalesce(new.audience_scope -> 'employee_ids', '[]')) <> 'array'
     or jsonb_typeof(coalesce(new.audience_scope -> 'team_ids', '[]')) <> 'array'
     or exists (
       select 1
       from jsonb_array_elements_text(
         coalesce(new.audience_scope -> 'employee_ids', '[]')
       ) as value
       where not exists (
         select 1 from app.employee_profiles as employee
         where employee.company_id = new.company_id and employee.id = value::uuid
       )
     )
     or exists (
       select 1
       from jsonb_array_elements_text(
         coalesce(new.audience_scope -> 'team_ids', '[]')
       ) as value
       where not exists (
         select 1 from app.teams as team
         where team.company_id = new.company_id and team.id = value::uuid
       )
     ) then
    raise exception using errcode = '22023', message = 'brief_audience_invalid';
  end if;
  insert into app.employee_brief_audience_grants (
    company_id, brief_version_id, principal_kind, employee_id
  )
  select new.company_id, new.id, 'employee', value::uuid
  from jsonb_array_elements_text(coalesce(new.audience_scope -> 'employee_ids', '[]')) as value
  join app.employee_profiles as employee
    on employee.company_id = new.company_id and employee.id = value::uuid
  on conflict do nothing;

  insert into app.employee_brief_audience_grants (
    company_id, brief_version_id, principal_kind, team_id
  )
  select new.company_id, new.id, 'team', value::uuid
  from jsonb_array_elements_text(coalesce(new.audience_scope -> 'team_ids', '[]')) as value
  join app.teams as team
    on team.company_id = new.company_id and team.id = value::uuid
  on conflict do nothing;
  return new;
exception when invalid_text_representation then
  raise exception using errcode = '22023', message = 'brief_audience_invalid';
end
$$;

create trigger employee_brief_materialize_audience
  after insert on app.employee_brief_versions
  for each row execute function app.materialize_employee_brief_audience();

insert into app.employee_brief_audience_grants (
  company_id, brief_version_id, principal_kind, employee_id
)
select brief.company_id, brief.id, 'employee', value::uuid
from app.employee_brief_versions as brief
cross join lateral jsonb_array_elements_text(
  coalesce(brief.audience_scope -> 'employee_ids', '[]')
) as value
join app.employee_profiles as employee
  on employee.company_id = brief.company_id and employee.id = value::uuid
on conflict do nothing;

insert into app.employee_brief_audience_grants (
  company_id, brief_version_id, principal_kind, team_id
)
select brief.company_id, brief.id, 'team', value::uuid
from app.employee_brief_versions as brief
cross join lateral jsonb_array_elements_text(
  coalesce(brief.audience_scope -> 'team_ids', '[]')
) as value
join app.teams as team
  on team.company_id = brief.company_id and team.id = value::uuid
on conflict do nothing;

create table app.task_events (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  task_id uuid not null,
  actor_membership_id uuid not null,
  event_type text not null check (event_type in (
    'acknowledged', 'started', 'blocked', 'unblocked', 'progress_reported',
    'estimate_flagged', 'skill_flagged', 'input_flagged', 'availability_flagged',
    'submitted', 'accepted', 'revision_requested'
  )),
  from_status text not null,
  to_status text not null,
  resulting_task_version bigint not null check (resulting_task_version > 0),
  event_payload jsonb not null check (jsonb_typeof(event_payload) = 'object'),
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  command_digest bytea not null check (octet_length(command_digest) = 32),
  correlation_id uuid not null,
  occurred_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, actor_membership_id, idempotency_key),
  foreign key (company_id, task_id) references app.work_items(company_id, task_id),
  foreign key (company_id, actor_membership_id)
    references app.company_memberships(company_id, id)
);

create table app.task_corrections (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  task_id uuid not null,
  event_id uuid not null,
  employee_id uuid not null,
  category text not null check (category in ('estimate', 'skill', 'input', 'availability')),
  correction_payload jsonb not null check (jsonb_typeof(correction_payload) = 'object'),
  status text not null default 'open' check (status in ('open', 'resolved', 'superseded')),
  created_at timestamptz not null default clock_timestamp(),
  resolved_at timestamptz null,
  unique (company_id, id),
  foreign key (company_id, task_id) references app.work_items(company_id, task_id),
  foreign key (company_id, event_id) references app.task_events(company_id, id),
  foreign key (company_id, employee_id)
    references app.employee_profiles(company_id, id),
  check ((status = 'resolved') = (resolved_at is not null))
);

create table app.submissions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  task_id uuid not null,
  submitting_employee_id uuid not null,
  accountable_employee_id uuid not null,
  review_policy_id uuid not null,
  version integer not null check (version > 0),
  narrative text not null check (length(btrim(narrative)) between 1 and 12000),
  external_evidence_refs jsonb not null default '[]'::jsonb
    check (jsonb_typeof(external_evidence_refs) = 'array'),
  submission_digest bytea not null check (octet_length(submission_digest) = 32),
  state text not null default 'submitted'
    check (state in ('submitted', 'superseded', 'accepted', 'revision_requested')),
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  command_digest bytea not null check (octet_length(command_digest) = 32),
  correlation_id uuid not null,
  resulting_task_version bigint not null check (resulting_task_version > 0),
  submitted_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, task_id, version),
  unique (company_id, submitting_employee_id, idempotency_key),
  foreign key (company_id, task_id) references app.work_items(company_id, task_id),
  foreign key (company_id, submitting_employee_id)
    references app.employee_profiles(company_id, id),
  foreign key (company_id, accountable_employee_id)
    references app.employee_profiles(company_id, id),
  foreign key (company_id, review_policy_id)
    references app.task_review_policies(company_id, id)
);

create unique index submissions_one_current
  on app.submissions (company_id, task_id)
  where state in ('submitted', 'accepted', 'revision_requested');

alter table app.private_files add column scan_state text not null default 'pending'
  check (scan_state in ('pending', 'clean', 'rejected', 'error'));
alter table app.private_files add column scan_engine_version text null
  check (scan_engine_version is null or length(scan_engine_version) <= 120);
alter table app.private_files add column scan_failure_code text null
  check (scan_failure_code is null or length(scan_failure_code) <= 120);

update app.private_files
set state = 'rejected', scan_state = 'error',
    scan_failure_code = 'legacy_scan_evidence_missing'
where state = 'available';
update app.private_files set scan_state = 'rejected'
where state = 'rejected' and scan_state = 'pending';

alter table app.private_files add constraint private_files_state_scan_pair_check check (
  (state in ('pending_upload', 'quarantined') and scan_state = 'pending')
  or (state = 'available' and scan_state = 'clean'
      and content_sha256 is not null and scanned_at is not null
      and detected_mime_type is not null
      and nullif(btrim(scan_engine_version), '') is not null)
  or (state = 'rejected' and scan_state in ('rejected', 'error'))
  or state = 'deleted'
);

create table app.submission_files (
  company_id uuid not null,
  submission_id uuid not null,
  file_id uuid not null,
  attached_at timestamptz not null default clock_timestamp(),
  primary key (company_id, submission_id, file_id),
  unique (company_id, file_id),
  foreign key (company_id, submission_id)
    references app.submissions(company_id, id) on delete cascade,
  foreign key (company_id, file_id) references app.private_files(company_id, id)
);

create table app.task_reviews (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  task_id uuid not null,
  submission_id uuid not null,
  submission_version integer not null check (submission_version > 0),
  submission_digest bytea not null check (octet_length(submission_digest) = 32),
  reviewer_employee_id uuid not null,
  review_policy_id uuid not null,
  review_policy_version integer not null check (review_policy_version > 0),
  decision text not null check (decision in ('accepted', 'revision_requested')),
  criterion_findings jsonb not null default '[]'::jsonb
    check (jsonb_typeof(criterion_findings) = 'array'),
  correction_request text null check (
    correction_request is null or length(correction_request) between 1 and 4000
  ),
  self_certification_rule text null,
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  command_digest bytea not null check (octet_length(command_digest) = 32),
  correlation_id uuid not null,
  resulting_task_version bigint not null check (resulting_task_version > 0),
  reviewed_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, reviewer_employee_id, idempotency_key),
  unique (company_id, submission_id),
  foreign key (company_id, task_id) references app.work_items(company_id, task_id),
  foreign key (company_id, submission_id) references app.submissions(company_id, id),
  foreign key (company_id, reviewer_employee_id)
    references app.employee_profiles(company_id, id),
  foreign key (company_id, review_policy_id)
    references app.task_review_policies(company_id, id),
  check ((decision = 'revision_requested') = (correction_request is not null))
);

create table app.employee_workload_state (
  company_id uuid not null,
  employee_id uuid not null,
  assigned_count integer not null default 0 check (assigned_count >= 0),
  in_progress_count integer not null default 0 check (in_progress_count >= 0),
  blocked_count integer not null default 0 check (blocked_count >= 0),
  submitted_count integer not null default 0 check (submitted_count >= 0),
  last_event_at timestamptz null,
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  primary key (company_id, employee_id),
  foreign key (company_id, employee_id)
    references app.employee_profiles(company_id, id)
);

create table app.familiarity_evidence (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  employee_id uuid not null,
  project_id uuid null,
  task_id uuid not null,
  submission_id uuid null,
  contribution_stage text not null check (contribution_stage in ('exposed', 'submitted', 'accepted')),
  evidence_digest bytea not null check (octet_length(evidence_digest) = 32),
  last_engaged_at timestamptz not null default clock_timestamp(),
  accepted_at timestamptz null,
  correction_state text not null default 'current'
    check (correction_state in ('current', 'disputed', 'superseded')),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique nulls not distinct (
    company_id, employee_id, task_id, submission_id, contribution_stage
  ),
  foreign key (company_id, employee_id)
    references app.employee_profiles(company_id, id),
  foreign key (company_id, project_id) references app.projects(company_id, id),
  foreign key (company_id, task_id) references app.work_items(company_id, task_id),
  foreign key (company_id, submission_id) references app.submissions(company_id, id),
  check ((contribution_stage = 'accepted') = (accepted_at is not null))
);

create table app.effort_observations (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  task_id uuid not null,
  employee_id uuid not null,
  submission_id uuid null,
  review_id uuid null,
  evidence_maturity text not null check (evidence_maturity in ('provisional', 'accepted', 'corrected')),
  correction_state text not null default 'current'
    check (correction_state in ('current', 'disputed', 'superseded')),
  reported_active_minutes integer null check (reported_active_minutes is null or reported_active_minutes >= 0),
  provenance text not null check (provenance in ('employee_report', 'lifecycle', 'review')),
  comparable boolean not null default false,
  observed_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  foreign key (company_id, task_id) references app.work_items(company_id, task_id),
  foreign key (company_id, employee_id)
    references app.employee_profiles(company_id, id),
  foreign key (company_id, submission_id) references app.submissions(company_id, id),
  foreign key (company_id, review_id) references app.task_reviews(company_id, id)
);

create or replace function app.employee_id_for_actor(p_company_id uuid, p_user_id uuid)
returns uuid
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select employee.id
  from app.employee_profiles as employee
  join app.company_memberships as membership
    on membership.company_id = employee.company_id
   and membership.id = employee.membership_id
  where employee.company_id = p_company_id
    and membership.user_id = p_user_id
    and membership.membership_status = 'active'
    and employee.status = 'active'
$$;

create or replace function app.can_read_task(p_user_id uuid, p_company_id uuid, p_task_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
      select 1
      from app.work_assignments as assignment
      join app.execution_resources as resource
        on resource.company_id = assignment.company_id
       and resource.id = assignment.resource_id
       and resource.status = 'active'
      where assignment.company_id = p_company_id
        and assignment.task_id = p_task_id
        and assignment.active
        and resource.employee_id = app.employee_id_for_actor(p_company_id, p_user_id)
    )
    or exists (
      select 1 from app.task_access_grants as task_access
      where task_access.company_id = p_company_id
        and task_access.task_id = p_task_id
        and task_access.active
        and task_access.employee_id = app.employee_id_for_actor(p_company_id, p_user_id)
    )
    or exists (
      select 1 from app.task_review_policies as policy
      where policy.company_id = p_company_id
        and policy.task_id = p_task_id
        and policy.active
        and policy.reviewer_employee_id = app.employee_id_for_actor(p_company_id, p_user_id)
    )
    or exists (
      select 1 from app.submissions as submission
      join app.task_review_policies as policy
        on policy.company_id = submission.company_id
       and policy.id = submission.review_policy_id
      where submission.company_id = p_company_id
        and submission.task_id = p_task_id and submission.state = 'submitted'
        and policy.reviewer_employee_id = app.employee_id_for_actor(p_company_id, p_user_id)
    )
$$;

create or replace function app.can_read_employee_brief(
  p_user_id uuid,
  p_company_id uuid,
  p_brief_version_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1
    from app.employee_brief_versions as brief
    join app.plan_approval_requirements as requirement
      on requirement.company_id = brief.company_id
     and requirement.plan_id = brief.plan_id
     and requirement.approval_domain = 'disclosure'
     and requirement.artifact_digest = brief.brief_digest
    join lateral (
      select decision.*
      from app.plan_approval_decisions as decision
      where decision.company_id = requirement.company_id
        and decision.requirement_id = requirement.id
      order by decision.decided_at desc, decision.id desc limit 1
    ) as latest on true
    join app.company_memberships as approver
      on approver.company_id = latest.company_id
     and approver.id = latest.actor_membership_id
     and approver.membership_status = 'active'
    where brief.company_id = p_company_id
      and brief.id = p_brief_version_id
      and latest.decision = 'approved'
      and latest.expires_at > clock_timestamp()
      and latest.artifact_digest = brief.brief_digest
      and app.actor_satisfies_plan_requirement(
        p_company_id, approver.user_id, requirement.id
      )
      and exists (
        select 1
        from app.employee_brief_audience_grants as audience
        where audience.company_id = brief.company_id
          and audience.brief_version_id = brief.id
          and audience.revoked_at is null
          and (
            audience.employee_id = app.employee_id_for_actor(p_company_id, p_user_id)
            or exists (
              select 1 from app.team_memberships as team_member
              where team_member.company_id = p_company_id
                and team_member.team_id = audience.team_id
                and team_member.employee_id = app.employee_id_for_actor(p_company_id, p_user_id)
                and team_member.valid_from <= clock_timestamp()
                and (team_member.valid_to is null or team_member.valid_to > clock_timestamp())
            )
          )
      )
  )
$$;

create or replace function app.can_manage_task(
  p_user_id uuid,
  p_company_id uuid,
  p_task_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1 from app.task_access_grants as task_access
    where task_access.company_id = p_company_id
      and task_access.task_id = p_task_id
      and task_access.access_role = 'manager' and task_access.active
      and task_access.employee_id = app.employee_id_for_actor(p_company_id, p_user_id)
  )
$$;

create or replace function app.task_reviewer_display_name(
  p_user_id uuid,
  p_company_id uuid,
  p_policy_id uuid
)
returns text
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select profile.display_name
  from app.task_review_policies as policy
  join app.employee_profiles as employee
    on employee.company_id = policy.company_id
   and employee.id = policy.reviewer_employee_id
  join app.company_memberships as membership
    on membership.company_id = employee.company_id
   and membership.id = employee.membership_id
   and membership.membership_status = 'active'
  join app.user_profiles as profile on profile.user_id = membership.user_id
  where policy.company_id = p_company_id and policy.id = p_policy_id
    and app.can_read_task(p_user_id, policy.company_id, policy.task_id)
$$;

create or replace function app.task_employee_display_name(
  p_user_id uuid,
  p_company_id uuid,
  p_task_id uuid,
  p_employee_id uuid
)
returns text
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select profile.display_name
  from app.employee_profiles as employee
  join app.company_memberships as membership
    on membership.company_id = employee.company_id
   and membership.id = employee.membership_id
   and membership.membership_status = 'active'
  join app.user_profiles as profile on profile.user_id = membership.user_id
  where employee.company_id = p_company_id and employee.id = p_employee_id
    and app.can_read_task(p_user_id, p_company_id, p_task_id)
    and (
      exists (
        select 1 from app.work_assignments as assignment
        join app.execution_resources as resource
          on resource.company_id = assignment.company_id
         and resource.id = assignment.resource_id
        where assignment.company_id = p_company_id and assignment.task_id = p_task_id
          and assignment.active and resource.employee_id = p_employee_id
      )
      or exists (
        select 1 from app.submissions as submission
        where submission.company_id = p_company_id and submission.task_id = p_task_id
          and submission.submitting_employee_id = p_employee_id
      )
    )
$$;

create or replace function app.can_manage_employee_brief(
  p_user_id uuid,
  p_company_id uuid,
  p_brief_version_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1 from app.employee_brief_versions as brief
    where brief.company_id = p_company_id and brief.id = p_brief_version_id
      and (
        (not exists (
          select 1 from app.work_items as item
          where item.company_id = brief.company_id
            and item.employee_brief_version_id = brief.id
        ) and app.can_read_plan(brief.company_id, p_user_id, brief.plan_id))
        or exists (
          select 1 from app.work_items as item
          where item.company_id = brief.company_id
            and item.employee_brief_version_id = brief.id
            and app.can_manage_task(p_user_id, item.company_id, item.task_id)
        )
      )
  )
$$;

create or replace function app.refresh_employee_workload(
  p_company_id uuid,
  p_employee_id uuid
)
returns void
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  insert into app.employee_workload_state (
    company_id, employee_id, assigned_count, in_progress_count,
    blocked_count, submitted_count, last_event_at
  )
  select p_company_id, p_employee_id,
    count(distinct item.task_id) filter (
      where item.status in ('assigned', 'acknowledged')
    ),
    count(distinct item.task_id) filter (where item.status = 'in_progress'),
    count(distinct item.task_id) filter (where item.status = 'blocked'),
    count(distinct item.task_id) filter (where item.status = 'submitted'),
    max(event.occurred_at)
  from app.execution_resources as resource
  left join app.work_assignments as assignment
    on assignment.company_id = resource.company_id
   and assignment.resource_id = resource.id
   and assignment.assignment_role = 'owner'
   and assignment.active
  left join app.work_items as item
    on item.company_id = assignment.company_id and item.task_id = assignment.task_id
  left join app.task_events as event
    on event.company_id = item.company_id and event.task_id = item.task_id
  where resource.company_id = p_company_id and resource.employee_id = p_employee_id
  group by resource.company_id, resource.employee_id
  on conflict (company_id, employee_id) do update
  set assigned_count = excluded.assigned_count,
      in_progress_count = excluded.in_progress_count,
      blocked_count = excluded.blocked_count,
      submitted_count = excluded.submitted_count,
      last_event_at = excluded.last_event_at,
      updated_at = clock_timestamp(),
      row_version = app.employee_workload_state.row_version + 1;
end
$$;

create or replace function app.refresh_assignment_workload()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_employee_id uuid;
begin
  if tg_op in ('UPDATE', 'DELETE') then
    select employee_id into v_employee_id from app.execution_resources
    where company_id = old.company_id and id = old.resource_id;
    if v_employee_id is not null then
      perform app.refresh_employee_workload(old.company_id, v_employee_id);
    end if;
  end if;
  if tg_op in ('INSERT', 'UPDATE') then
    select employee_id into v_employee_id from app.execution_resources
    where company_id = new.company_id and id = new.resource_id;
    if v_employee_id is not null then
      perform app.refresh_employee_workload(new.company_id, v_employee_id);
    end if;
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end
$$;

create trigger work_assignments_refresh_workload
  after insert or update or delete on app.work_assignments
  for each row execute function app.refresh_assignment_workload();

do $$
declare
  target record;
begin
  for target in
    select company_id, employee_id from app.execution_resources
    where employee_id is not null
  loop
    perform app.refresh_employee_workload(target.company_id, target.employee_id);
  end loop;
end
$$;

create or replace function app.set_task_review_policy(
  p_company_id uuid,
  p_task_id uuid,
  p_reviewer_employee_id uuid,
  p_self_certifiable boolean,
  p_self_certification_rule text,
  p_expected_task_version bigint,
  p_idempotency_key text,
  p_command_digest bytea,
  p_correlation_id uuid
)
returns table (
  policy_id uuid, policy_version integer, task_version bigint, replayed boolean
)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_membership_id uuid;
  v_item app.work_items%rowtype;
  v_existing app.task_review_policies%rowtype;
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id()
     or not app.can_manage_planning(p_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'manager_authority_required';
  end if;
  select id into v_membership_id from app.company_memberships
  where company_id = p_company_id and user_id = app.current_actor_id()
    and membership_status = 'active';

  perform pg_advisory_xact_lock(hashtextextended(
    p_company_id::text || ':' || v_membership_id::text || ':' || p_idempotency_key, 0
  ));
  select * into v_existing from app.task_review_policies
  where company_id = p_company_id and assigned_by_membership_id = v_membership_id
    and idempotency_key = p_idempotency_key;
  if found then
    if v_existing.command_digest <> p_command_digest then
      raise exception using errcode = '23505', message = 'idempotency_key_reused';
    end if;
    return query select v_existing.id, v_existing.version,
      v_existing.resulting_task_version, true;
    return;
  end if;

  select * into v_item from app.work_items
  where company_id = p_company_id and task_id = p_task_id
    and status not in ('accepted', 'cancelled') for update;
  if not found then
    raise exception using errcode = 'P0002', message = 'task_not_reviewable';
  end if;
  if v_item.row_version <> p_expected_task_version then
    raise exception using errcode = '40001', message = 'task_version_stale';
  end if;
  if p_reviewer_employee_id is not null and not exists (
    select 1 from app.employee_profiles where company_id = p_company_id
      and id = p_reviewer_employee_id and status = 'active'
  ) then
    raise exception using errcode = 'P0002', message = 'reviewer_not_found';
  end if;
  if not p_self_certifiable and exists (
    select 1 from app.work_assignments as assignment
    join app.execution_resources as resource
      on resource.company_id = assignment.company_id
     and resource.id = assignment.resource_id
    where assignment.company_id = p_company_id and assignment.task_id = p_task_id
      and assignment.active and assignment.assignment_role = 'owner'
      and resource.employee_id = p_reviewer_employee_id
  ) then
    raise exception using errcode = '22023', message = 'self_review_rule_required';
  end if;
  if (p_reviewer_employee_id is null and not p_self_certifiable)
     or p_self_certifiable <> (nullif(btrim(p_self_certification_rule), '') is not null)
     or octet_length(p_command_digest) <> 32 then
    raise exception using errcode = '22023', message = 'review_policy_invalid';
  end if;

  update app.task_review_policies set active = false, superseded_at = clock_timestamp()
  where company_id = p_company_id and task_id = p_task_id and active;
  insert into app.task_review_policies (
    company_id, task_id, version, reviewer_employee_id, self_certifiable,
    self_certification_rule, assigned_by_membership_id, idempotency_key,
    command_digest, correlation_id, resulting_task_version
  ) values (
    p_company_id, p_task_id,
    coalesce((select max(version) + 1 from app.task_review_policies
              where company_id = p_company_id and task_id = p_task_id), 1),
    p_reviewer_employee_id, p_self_certifiable,
    nullif(btrim(p_self_certification_rule), ''), v_membership_id,
    p_idempotency_key, p_command_digest, p_correlation_id, v_item.row_version + 1
  ) returning id, version into policy_id, policy_version;
  update app.work_items set updated_at = clock_timestamp()
  where company_id = p_company_id and task_id = p_task_id
  returning row_version into task_version;
  insert into app.outbox_intents (
    company_id, intent_kind, aggregate_type, aggregate_id, payload, correlation_id
  ) values (
    p_company_id, 'task.changed', 'task_review_policy', policy_id,
    jsonb_build_object('task_id', p_task_id, 'version', policy_version), p_correlation_id
  );
  replayed := false;
  return next;
end
$$;

create or replace function app.transition_employee_task(
  p_company_id uuid,
  p_task_id uuid,
  p_command text,
  p_expected_task_version bigint,
  p_payload jsonb,
  p_idempotency_key text,
  p_command_digest bytea,
  p_correlation_id uuid
)
returns table (event_id uuid, task_status text, task_version bigint, replayed boolean)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_membership_id uuid;
  v_employee_id uuid;
  v_item app.work_items%rowtype;
  v_existing app.task_events%rowtype;
  v_to_status text;
  v_event_type text;
  v_category text;
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id() then
    raise exception using errcode = '42501', message = 'request_context_invalid';
  end if;
  select id into v_membership_id from app.company_memberships
  where company_id = p_company_id and user_id = app.current_actor_id()
    and membership_status = 'active';
  v_employee_id := app.employee_id_for_actor(p_company_id, app.current_actor_id());
  if v_employee_id is null or not app.can_read_task(
    app.current_actor_id(), p_company_id, p_task_id
  ) then
    raise exception using errcode = 'P0002', message = 'task_not_found';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(
    p_company_id::text || ':' || v_membership_id::text || ':' || p_idempotency_key, 0
  ));

  select * into v_existing from app.task_events
  where company_id = p_company_id and actor_membership_id = v_membership_id
    and idempotency_key = p_idempotency_key;
  if found then
    if v_existing.command_digest <> p_command_digest then
      raise exception using errcode = '23505', message = 'idempotency_key_reused';
    end if;
    return query select v_existing.id, v_existing.to_status,
      v_existing.resulting_task_version, true;
    return;
  end if;

  select * into v_item from app.work_items
  where company_id = p_company_id and task_id = p_task_id for update;
  if not found then
    raise exception using errcode = 'P0002', message = 'task_not_found';
  end if;
  if v_item.row_version <> p_expected_task_version then
    raise exception using errcode = '40001', message = 'task_version_stale';
  end if;
  if jsonb_typeof(p_payload) <> 'object' or octet_length(p_command_digest) <> 32 then
    raise exception using errcode = '22023', message = 'task_command_invalid';
  end if;
  if not exists (
    select 1 from app.work_assignments as assignment
    join app.execution_resources as resource
      on resource.company_id = assignment.company_id and resource.id = assignment.resource_id
    where assignment.company_id = p_company_id and assignment.task_id = p_task_id
      and assignment.active and assignment.assignment_role = 'owner'
      and resource.employee_id = v_employee_id
  ) then
    raise exception using errcode = '42501', message = 'task_owner_required';
  end if;

  v_to_status := v_item.status;
  if p_command = 'acknowledge' and v_item.status = 'assigned' then
    v_to_status := 'acknowledged'; v_event_type := 'acknowledged';
  elsif p_command = 'start' and v_item.status = 'acknowledged' then
    v_to_status := 'in_progress'; v_event_type := 'started';
  elsif p_command = 'block' and v_item.status = 'in_progress' then
    v_to_status := 'blocked'; v_event_type := 'blocked';
  elsif p_command = 'unblock' and v_item.status = 'blocked' then
    v_to_status := 'in_progress'; v_event_type := 'unblocked';
  elsif p_command = 'progress' and v_item.status in ('in_progress', 'blocked') then
    v_event_type := 'progress_reported';
  elsif p_command in ('flag_estimate', 'flag_skill', 'flag_input', 'flag_availability')
        and v_item.status not in ('accepted', 'cancelled') then
    v_event_type := case p_command
      when 'flag_estimate' then 'estimate_flagged'
      when 'flag_skill' then 'skill_flagged'
      when 'flag_input' then 'input_flagged'
      else 'availability_flagged' end;
    v_category := case p_command
      when 'flag_estimate' then 'estimate'
      when 'flag_skill' then 'skill'
      when 'flag_input' then 'input'
      else 'availability' end;
  else
    raise exception using errcode = '22023', message = 'task_transition_invalid';
  end if;

  if v_to_status <> v_item.status then
    update app.work_items set status = v_to_status
    where company_id = p_company_id and task_id = p_task_id
    returning row_version into task_version;
  else
    task_version := v_item.row_version;
  end if;
  insert into app.task_events (
    company_id, task_id, actor_membership_id, event_type, from_status,
    to_status, resulting_task_version, event_payload, idempotency_key,
    command_digest, correlation_id
  ) values (
    p_company_id, p_task_id, v_membership_id, v_event_type, v_item.status,
    v_to_status, task_version,
    case when v_category is null then p_payload
         else jsonb_build_object('category', v_category) end,
    p_idempotency_key,
    p_command_digest, p_correlation_id
  ) returning id into event_id;

  if v_category is not null then
    insert into app.task_corrections (
      company_id, task_id, event_id, employee_id, category, correction_payload
    ) values (p_company_id, p_task_id, event_id, v_employee_id, v_category, p_payload);
  end if;
  if v_event_type = 'started' then
    insert into app.familiarity_evidence (
      company_id, employee_id, project_id, task_id, contribution_stage, evidence_digest
    ) values (
      p_company_id, v_employee_id, v_item.project_id, p_task_id, 'exposed', p_command_digest
    ) on conflict do nothing;
  end if;
  perform app.refresh_employee_workload(p_company_id, v_employee_id);
  insert into app.outbox_intents (
    company_id, intent_kind, aggregate_type, aggregate_id, payload, correlation_id
  ) values (
    p_company_id, 'task.changed', 'task', p_task_id,
    jsonb_build_object('event_id', event_id, 'status', v_to_status), p_correlation_id
  );
  task_status := v_to_status;
  replayed := false;
  return next;
end
$$;

create or replace function app.record_private_file_scan(
  p_company_id uuid,
  p_file_id uuid,
  p_verdict text,
  p_detected_mime_type text,
  p_observed_size_bytes bigint,
  p_content_sha256 bytea,
  p_scan_engine_version text,
  p_final_object_path text
)
returns text
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_file app.private_files%rowtype;
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id() then
    raise exception using errcode = '42501', message = 'request_context_invalid';
  end if;
  select * into v_file from app.private_files
  where company_id = p_company_id and id = p_file_id for update;
  if not found or v_file.state <> 'quarantined' or v_file.scan_state <> 'pending' then
    raise exception using errcode = '22023', message = 'file_scan_state_invalid';
  end if;
  if p_verdict = 'clean' then
    if p_detected_mime_type <> v_file.declared_mime_type
       or p_observed_size_bytes <> v_file.size_bytes
       or p_content_sha256 is null or octet_length(p_content_sha256) <> 32
       or nullif(btrim(p_scan_engine_version), '') is null
       or p_final_object_path not like p_company_id::text || '/' || p_file_id::text || '/%'
       or p_final_object_path = v_file.object_path then
      raise exception using errcode = '22023', message = 'file_scan_evidence_invalid';
    end if;
    update app.private_files set state = 'available', scan_state = 'clean',
      bucket_id = 'coordination-private', object_path = p_final_object_path,
      detected_mime_type = p_detected_mime_type, size_bytes = p_observed_size_bytes,
      content_sha256 = p_content_sha256, scan_engine_version = p_scan_engine_version,
      scanned_at = clock_timestamp()
    where company_id = p_company_id and id = p_file_id;
    return 'available';
  elsif p_verdict = 'rejected' then
    update app.private_files set state = 'rejected', scan_state = 'rejected',
      detected_mime_type = p_detected_mime_type, size_bytes = p_observed_size_bytes,
      content_sha256 = p_content_sha256, scan_engine_version = p_scan_engine_version,
      scan_failure_code = 'scanner_rejected', scanned_at = clock_timestamp()
    where company_id = p_company_id and id = p_file_id;
    return 'rejected';
  end if;
  raise exception using errcode = '22023', message = 'file_scan_verdict_invalid';
end
$$;

create or replace function app.submit_employee_task(
  p_company_id uuid,
  p_task_id uuid,
  p_narrative text,
  p_external_evidence_refs jsonb,
  p_file_ids jsonb,
  p_reported_active_minutes integer,
  p_expected_task_version bigint,
  p_submission_digest bytea,
  p_idempotency_key text,
  p_command_digest bytea,
  p_correlation_id uuid
)
returns table (
  submission_id uuid, submission_version integer, submission_state text,
  task_version bigint, replayed boolean
)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_membership_id uuid;
  v_employee_id uuid;
  v_item app.work_items%rowtype;
  v_existing app.submissions%rowtype;
  v_policy app.task_review_policies%rowtype;
  v_file_count integer;
  v_event_id uuid;
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id() then
    raise exception using errcode = '42501', message = 'request_context_invalid';
  end if;
  select id into v_membership_id from app.company_memberships
  where company_id = p_company_id and user_id = app.current_actor_id()
    and membership_status = 'active';
  v_employee_id := app.employee_id_for_actor(p_company_id, app.current_actor_id());
  perform pg_advisory_xact_lock(hashtextextended(
    p_company_id::text || ':' || v_membership_id::text || ':' || p_idempotency_key, 0
  ));
  select * into v_existing from app.submissions
  where company_id = p_company_id and submitting_employee_id = v_employee_id
    and idempotency_key = p_idempotency_key;
  if found then
    if v_existing.command_digest <> p_command_digest then
      raise exception using errcode = '23505', message = 'idempotency_key_reused';
    end if;
    return query select v_existing.id, v_existing.version, v_existing.state,
      v_existing.resulting_task_version, true;
    return;
  end if;

  select * into v_item from app.work_items
  where company_id = p_company_id and task_id = p_task_id for update;
  if not found or v_item.row_version <> p_expected_task_version
     or v_item.status not in ('in_progress', 'blocked', 'revision_requested') then
    raise exception using errcode = '40001', message = 'task_version_or_state_stale';
  end if;
  if not exists (
    select 1 from app.work_assignments as assignment
    join app.execution_resources as resource
      on resource.company_id = assignment.company_id and resource.id = assignment.resource_id
    where assignment.company_id = p_company_id and assignment.task_id = p_task_id
      and assignment.active and assignment.assignment_role = 'owner'
      and resource.employee_id = v_employee_id
  ) then
    raise exception using errcode = '42501', message = 'task_owner_required';
  end if;
  select * into v_policy from app.task_review_policies
  where company_id = p_company_id and task_id = p_task_id and active;
  if not found then
    raise exception using errcode = '42501', message = 'review_policy_required';
  end if;
  if jsonb_typeof(p_external_evidence_refs) <> 'array'
     or jsonb_typeof(p_file_ids) <> 'array'
     or nullif(btrim(p_narrative), '') is null
     or length(p_narrative) > 12000
     or p_reported_active_minutes not between 0 and 100000
     or octet_length(p_submission_digest) <> 32
     or octet_length(p_command_digest) <> 32 then
    raise exception using errcode = '22023', message = 'submission_payload_invalid';
  end if;
  if jsonb_array_length(p_external_evidence_refs) > 50
     or jsonb_array_length(p_file_ids) > 20
     or exists (
       select 1 from jsonb_array_elements(p_external_evidence_refs) as evidence
       where jsonb_typeof(evidence) <> 'string'
          or length(btrim(evidence #>> '{}')) not between 1 and 500
     )
     or (select count(*) from jsonb_array_elements_text(p_external_evidence_refs)) <>
        (select count(distinct value) from jsonb_array_elements_text(p_external_evidence_refs))
     or (select count(*) from jsonb_array_elements_text(p_file_ids)) <>
        (select count(distinct value) from jsonb_array_elements_text(p_file_ids)) then
    raise exception using errcode = '22023', message = 'submission_payload_invalid';
  end if;

  select count(*) into v_file_count from jsonb_array_elements_text(p_file_ids);
  if v_file_count <> (
    select count(*) from app.private_files as file
    where file.company_id = p_company_id
      and file.id in (select value::uuid from jsonb_array_elements_text(p_file_ids))
      and file.uploader_employee_id = v_employee_id
      and file.purpose = 'submission'
      and file.state = 'available' and file.scan_state = 'clean'
      and file.content_sha256 is not null
      and not exists (
        select 1 from app.submission_files as used
        where used.company_id = file.company_id and used.file_id = file.id
      )
  ) then
    raise exception using errcode = '22023', message = 'submission_file_not_clean_or_authorized';
  end if;

  update app.submissions set state = 'superseded'
  where company_id = p_company_id and task_id = p_task_id
    and state = 'revision_requested';
  submission_version := coalesce((
    select max(version) + 1 from app.submissions
    where company_id = p_company_id and task_id = p_task_id
  ), 1);
  update app.work_items set status = 'submitted'
  where company_id = p_company_id and task_id = p_task_id
  returning row_version into task_version;
  insert into app.submissions (
    company_id, task_id, submitting_employee_id, accountable_employee_id,
    review_policy_id, version, narrative, external_evidence_refs, submission_digest,
    idempotency_key, command_digest, correlation_id, resulting_task_version
  ) values (
    p_company_id, p_task_id, v_employee_id, v_employee_id,
    v_policy.id, submission_version, p_narrative, p_external_evidence_refs,
    p_submission_digest, p_idempotency_key, p_command_digest, p_correlation_id,
    task_version
  ) returning id, state into submission_id, submission_state;

  insert into app.submission_files (company_id, submission_id, file_id)
  select p_company_id, submission_id, value::uuid from jsonb_array_elements_text(p_file_ids);
  insert into app.task_events (
    company_id, task_id, actor_membership_id, event_type, from_status,
    to_status, resulting_task_version, event_payload, idempotency_key,
    command_digest, correlation_id
  ) values (
    p_company_id, p_task_id, v_membership_id, 'submitted', v_item.status,
    'submitted', task_version, jsonb_build_object(
      'submission_id', submission_id, 'submission_version', submission_version
    ), 'event:' || encode(p_command_digest, 'hex'), p_command_digest, p_correlation_id
  ) returning id into v_event_id;
  insert into app.familiarity_evidence (
    company_id, employee_id, project_id, task_id, submission_id,
    contribution_stage, evidence_digest
  ) values (
    p_company_id, v_employee_id, v_item.project_id, p_task_id, submission_id,
    'submitted', p_submission_digest
  );
  insert into app.effort_observations (
    company_id, task_id, employee_id, submission_id, evidence_maturity,
    reported_active_minutes, provenance, comparable
  ) values (
    p_company_id, p_task_id, v_employee_id, submission_id, 'provisional',
    p_reported_active_minutes,
    case when p_reported_active_minutes is null then 'lifecycle' else 'employee_report' end,
    false
  );
  perform app.refresh_employee_workload(p_company_id, v_employee_id);
  insert into app.outbox_intents (
    company_id, intent_kind, aggregate_type, aggregate_id, payload, correlation_id
  ) values (
    p_company_id, 'task.changed', 'submission', submission_id,
    jsonb_build_object('task_id', p_task_id, 'state', 'submitted'), p_correlation_id
  );
  replayed := false;
  return next;
exception when invalid_text_representation then
  raise exception using errcode = '22023', message = 'submission_file_id_invalid';
end
$$;

create or replace function app.review_task_submission(
  p_company_id uuid,
  p_submission_id uuid,
  p_expected_submission_version integer,
  p_submission_digest bytea,
  p_decision text,
  p_criterion_findings jsonb,
  p_correction_request text,
  p_idempotency_key text,
  p_command_digest bytea,
  p_correlation_id uuid
)
returns table (
  review_id uuid, review_decision text, task_status text,
  task_version bigint, replayed boolean
)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_membership_id uuid;
  v_employee_id uuid;
  v_submission app.submissions%rowtype;
  v_item app.work_items%rowtype;
  v_policy app.task_review_policies%rowtype;
  v_existing app.task_reviews%rowtype;
  v_event_id uuid;
  v_review_id uuid;
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id() then
    raise exception using errcode = '42501', message = 'request_context_invalid';
  end if;
  select id into v_membership_id from app.company_memberships
  where company_id = p_company_id and user_id = app.current_actor_id()
    and membership_status = 'active';
  v_employee_id := app.employee_id_for_actor(p_company_id, app.current_actor_id());
  perform pg_advisory_xact_lock(hashtextextended(
    p_company_id::text || ':' || v_membership_id::text || ':' || p_idempotency_key, 0
  ));
  select * into v_existing from app.task_reviews
  where company_id = p_company_id and reviewer_employee_id = v_employee_id
    and idempotency_key = p_idempotency_key;
  if found then
    if v_existing.command_digest <> p_command_digest then
      raise exception using errcode = '23505', message = 'idempotency_key_reused';
    end if;
    return query select v_existing.id, v_existing.decision,
      v_existing.decision, v_existing.resulting_task_version, true;
    return;
  end if;

  select * into v_submission from app.submissions
  where company_id = p_company_id and id = p_submission_id for update;
  if not found or v_submission.version <> p_expected_submission_version
     or v_submission.submission_digest <> p_submission_digest
     or v_submission.state <> 'submitted' then
    raise exception using errcode = '40001', message = 'submission_version_stale';
  end if;
  select * into v_item from app.work_items
  where company_id = p_company_id and task_id = v_submission.task_id for update;
  if v_item.status <> 'submitted' then
    raise exception using errcode = '40001', message = 'task_submission_state_stale';
  end if;
  select * into v_policy from app.task_review_policies
  where company_id = p_company_id and id = v_submission.review_policy_id;
  if not found or not (
    (v_policy.reviewer_employee_id = v_employee_id
      and v_submission.submitting_employee_id <> v_employee_id)
    or (v_policy.self_certifiable and v_submission.submitting_employee_id = v_employee_id)
  ) then
    raise exception using errcode = '42501', message = 'assigned_reviewer_required';
  end if;
  if p_decision not in ('accepted', 'revision_requested')
     or (p_decision = 'revision_requested' and nullif(btrim(p_correction_request), '') is null)
     or (p_decision = 'accepted' and nullif(btrim(p_correction_request), '') is not null) then
    raise exception using errcode = '22023', message = 'review_decision_invalid';
  end if;
  if jsonb_typeof(p_criterion_findings) <> 'array'
     or jsonb_array_length(p_criterion_findings) > 100
     or exists (
       select 1 from jsonb_array_elements(p_criterion_findings) as finding
       where jsonb_typeof(finding) <> 'object'
     )
     or p_expected_submission_version <= 0
     or octet_length(p_submission_digest) <> 32
     or octet_length(p_command_digest) <> 32 then
    raise exception using errcode = '22023', message = 'review_payload_invalid';
  end if;

  update app.submissions set state = p_decision
  where company_id = p_company_id and id = p_submission_id;
  update app.work_items set status = p_decision
  where company_id = p_company_id and task_id = v_submission.task_id
  returning row_version into task_version;
  insert into app.task_reviews (
    company_id, task_id, submission_id, submission_version, submission_digest,
    reviewer_employee_id, review_policy_id, review_policy_version,
    decision, criterion_findings, correction_request,
    self_certification_rule, idempotency_key, command_digest, correlation_id
    , resulting_task_version
  ) values (
    p_company_id, v_submission.task_id, p_submission_id, v_submission.version,
    v_submission.submission_digest, v_employee_id, v_policy.id, v_policy.version,
    p_decision, p_criterion_findings,
    nullif(btrim(p_correction_request), ''),
    case when v_submission.submitting_employee_id = v_employee_id
         then v_policy.self_certification_rule end,
    p_idempotency_key, p_command_digest, p_correlation_id, task_version
  ) returning id, decision into v_review_id, review_decision;
  insert into app.task_events (
    company_id, task_id, actor_membership_id, event_type, from_status,
    to_status, resulting_task_version, event_payload, idempotency_key,
    command_digest, correlation_id
  ) values (
    p_company_id, v_submission.task_id, v_membership_id, p_decision,
    'submitted', p_decision, task_version,
    jsonb_build_object('submission_id', p_submission_id, 'review_id', v_review_id),
    'event:' || encode(p_command_digest, 'hex'), p_command_digest, p_correlation_id
  ) returning id into v_event_id;

  if p_decision = 'accepted' then
    update app.familiarity_evidence set correction_state = 'superseded'
    where company_id = p_company_id and submission_id = p_submission_id
      and contribution_stage = 'submitted' and correction_state = 'current';
    update app.effort_observations set correction_state = 'superseded'
    where company_id = p_company_id and submission_id = p_submission_id
      and evidence_maturity = 'provisional' and correction_state = 'current';
    insert into app.familiarity_evidence (
      company_id, employee_id, project_id, task_id, submission_id,
      contribution_stage, evidence_digest, accepted_at
    ) values (
      p_company_id, v_submission.submitting_employee_id, v_item.project_id,
      v_submission.task_id, p_submission_id, 'accepted',
      v_submission.submission_digest, clock_timestamp()
    );
    insert into app.effort_observations (
      company_id, task_id, employee_id, submission_id, review_id,
      evidence_maturity, reported_active_minutes, provenance, comparable
    ) select
      p_company_id, v_submission.task_id, v_submission.submitting_employee_id,
      p_submission_id, v_review_id, 'accepted', provisional.reported_active_minutes,
      'review', true
    from app.effort_observations as provisional
    where provisional.company_id = p_company_id
      and provisional.submission_id = p_submission_id
      and provisional.evidence_maturity = 'provisional'
    order by provisional.observed_at desc limit 1;
    update app.employee_profiles set profile_revision = profile_revision + 1
    where company_id = p_company_id and id = v_submission.submitting_employee_id;
  else
    update app.familiarity_evidence set correction_state = 'disputed'
    where company_id = p_company_id and submission_id = p_submission_id
      and contribution_stage = 'submitted' and correction_state = 'current';
    update app.effort_observations set correction_state = 'disputed',
      evidence_maturity = 'corrected', comparable = false
    where company_id = p_company_id and submission_id = p_submission_id
      and evidence_maturity = 'provisional' and correction_state = 'current';
  end if;
  perform app.refresh_employee_workload(
    p_company_id, v_submission.submitting_employee_id
  );
  insert into app.outbox_intents (
    company_id, intent_kind, aggregate_type, aggregate_id, payload, correlation_id
  ) values (
    p_company_id, 'task.changed', 'submission', p_submission_id,
    jsonb_build_object('task_id', v_submission.task_id, 'state', p_decision),
    p_correlation_id
  );
  task_status := p_decision;
  review_id := v_review_id;
  replayed := false;
  return next;
end
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
      on uploader.company_id = file.company_id and uploader.id = file.uploader_employee_id
    join app.company_memberships as uploader_membership
      on uploader_membership.company_id = uploader.company_id
     and uploader_membership.id = uploader.membership_id
    where file.company_id = p_company_id and file.id = p_file_id
      and file.state = 'available' and file.scan_state = 'clean'
      and app.has_active_membership(p_company_id, p_user_id)
      and (
        (file.purpose <> 'submission' and app.is_company_admin(p_company_id, p_user_id))
        or uploader_membership.user_id = p_user_id
        or (file.purpose = 'source' and file.source_id is not null and app.can_read_source(
          p_user_id, p_company_id, file.source_id
        ))
        or exists (
          select 1 from app.submission_files as linked
          join app.submissions as submission
            on submission.company_id = linked.company_id
           and submission.id = linked.submission_id
          where linked.company_id = file.company_id and linked.file_id = file.id
            and app.can_read_task(p_user_id, submission.company_id, submission.task_id)
        )
      )
  )
$$;

revoke execute on function app.create_employee_execution_resource() from public;
revoke execute on function app.bind_work_item_execution_context() from public;
revoke execute on function app.grant_committed_task_manager_access() from public;
revoke execute on function app.materialize_employee_brief_audience() from public;
revoke execute on function app.employee_id_for_actor(uuid, uuid) from public;
revoke execute on function app.can_read_task(uuid, uuid, uuid) from public;
revoke execute on function app.can_read_employee_brief(uuid, uuid, uuid) from public;
revoke execute on function app.can_manage_task(uuid, uuid, uuid) from public;
revoke execute on function app.task_reviewer_display_name(uuid, uuid, uuid) from public;
revoke execute on function app.task_employee_display_name(uuid, uuid, uuid, uuid) from public;
revoke execute on function app.can_manage_employee_brief(uuid, uuid, uuid) from public;
revoke execute on function app.refresh_employee_workload(uuid, uuid) from public;
revoke execute on function app.refresh_assignment_workload() from public;
revoke execute on function app.set_task_review_policy(
  uuid, uuid, uuid, boolean, text, bigint, text, bytea, uuid
) from public;
revoke execute on function app.transition_employee_task(
  uuid, uuid, text, bigint, jsonb, text, bytea, uuid
) from public;
revoke execute on function app.record_private_file_scan(
  uuid, uuid, text, text, bigint, bytea, text, text
) from public;
revoke execute on function app.submit_employee_task(
  uuid, uuid, text, jsonb, jsonb, integer, bigint, bytea, text, bytea, uuid
) from public;
revoke execute on function app.review_task_submission(
  uuid, uuid, integer, bytea, text, jsonb, text, text, bytea, uuid
) from public;

grant execute on function app.create_employee_execution_resource() to coordination_worker;
grant execute on function app.materialize_employee_brief_audience() to coordination_worker;
grant execute on function app.employee_id_for_actor(uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.can_read_task(uuid, uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.can_read_employee_brief(uuid, uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.can_manage_task(uuid, uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.task_reviewer_display_name(uuid, uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.task_employee_display_name(uuid, uuid, uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.can_manage_employee_brief(uuid, uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.refresh_employee_workload(uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.set_task_review_policy(
  uuid, uuid, uuid, boolean, text, bigint, text, bytea, uuid
) to coordination_api;
grant execute on function app.transition_employee_task(
  uuid, uuid, text, bigint, jsonb, text, bytea, uuid
) to coordination_api;
grant execute on function app.record_private_file_scan(
  uuid, uuid, text, text, bigint, bytea, text, text
) to coordination_worker;
grant execute on function app.submit_employee_task(
  uuid, uuid, text, jsonb, jsonb, integer, bigint, bytea, text, bytea, uuid
) to coordination_api;
grant execute on function app.review_task_submission(
  uuid, uuid, integer, bytea, text, jsonb, text, text, bytea, uuid
) to coordination_api;

drop policy work_items_company_select on app.work_items;
drop policy work_assignments_company_select on app.work_assignments;
drop policy committed_schedule_company_select on app.committed_schedule_blocks;
drop policy employee_briefs_manager_select on app.employee_brief_versions;

alter table app.execution_resources enable row level security;
alter table app.task_review_policies enable row level security;
alter table app.task_access_grants enable row level security;
alter table app.employee_brief_audience_grants enable row level security;
alter table app.task_events enable row level security;
alter table app.task_corrections enable row level security;
alter table app.submissions enable row level security;
alter table app.submission_files enable row level security;
alter table app.task_reviews enable row level security;
alter table app.employee_workload_state enable row level security;
alter table app.familiarity_evidence enable row level security;
alter table app.effort_observations enable row level security;

create policy work_items_authorized_select on app.work_items
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_task(app.current_actor_id(), company_id, task_id));
create policy work_assignments_authorized_select on app.work_assignments
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_task(app.current_actor_id(), company_id, task_id));
create policy committed_schedule_authorized_select on app.committed_schedule_blocks
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_task(app.current_actor_id(), company_id, task_id));
create policy execution_resources_authorized_select on app.execution_resources
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and (employee_id = app.employee_id_for_actor(company_id, app.current_actor_id())
      or app.can_manage_planning(company_id, app.current_actor_id())));
create policy task_review_policies_authorized_select on app.task_review_policies
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_task(app.current_actor_id(), company_id, task_id));
create policy task_access_grants_authorized_select on app.task_access_grants
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and (employee_id = app.employee_id_for_actor(company_id, app.current_actor_id())
      or app.can_manage_task(app.current_actor_id(), company_id, task_id)));
create policy brief_audience_authorized_select on app.employee_brief_audience_grants
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and (app.can_read_employee_brief(
      app.current_actor_id(), company_id, brief_version_id
    ) or app.can_manage_planning(company_id, app.current_actor_id())));
create policy employee_briefs_employee_select on app.employee_brief_versions
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_employee_brief(app.current_actor_id(), company_id, id));
create policy employee_briefs_planning_or_task_manager_select
  on app.employee_brief_versions
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_manage_employee_brief(app.current_actor_id(), company_id, id));
create policy task_events_authorized_select on app.task_events
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_task(app.current_actor_id(), company_id, task_id)
    and (event_type not in (
      'estimate_flagged', 'skill_flagged', 'input_flagged', 'availability_flagged'
    ) or exists (
      select 1 from app.company_memberships as actor_membership
      where actor_membership.company_id = task_events.company_id
        and actor_membership.id = task_events.actor_membership_id
        and actor_membership.user_id = app.current_actor_id()
        and actor_membership.membership_status = 'active'
    )
      or app.can_manage_task(app.current_actor_id(), company_id, task_id)));
create policy task_corrections_authorized_select on app.task_corrections
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and (employee_id = app.employee_id_for_actor(company_id, app.current_actor_id())
      or app.can_manage_task(app.current_actor_id(), company_id, task_id)));
create policy submissions_authorized_select on app.submissions
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_task(app.current_actor_id(), company_id, task_id));
create policy submission_files_authorized_select on app.submission_files
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and exists (select 1 from app.submissions as submission
      where submission.company_id = submission_files.company_id
        and submission.id = submission_files.submission_id
        and app.can_read_task(
          app.current_actor_id(), submission.company_id, submission.task_id
        )));
create policy task_reviews_authorized_select on app.task_reviews
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_task(app.current_actor_id(), company_id, task_id));
create policy workload_self_or_manager_select on app.employee_workload_state
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and (employee_id = app.employee_id_for_actor(company_id, app.current_actor_id())
      or app.can_manage_planning(company_id, app.current_actor_id())));
create policy familiarity_self_or_manager_select on app.familiarity_evidence
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and (employee_id = app.employee_id_for_actor(company_id, app.current_actor_id())
      or app.can_manage_planning(company_id, app.current_actor_id())));
create policy effort_self_or_manager_select on app.effort_observations
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and (employee_id = app.employee_id_for_actor(company_id, app.current_actor_id())
      or app.can_manage_planning(company_id, app.current_actor_id())));

grant select on app.execution_resources, app.task_review_policies, app.task_access_grants,
  app.employee_brief_audience_grants, app.task_events, app.task_corrections,
  app.submissions, app.submission_files, app.task_reviews,
  app.employee_workload_state, app.familiarity_evidence, app.effort_observations
  to coordination_api, coordination_worker;

create index work_assignments_resource_active_lookup
  on app.work_assignments (company_id, resource_id, active, task_id);
create index task_events_task_lookup on app.task_events (company_id, task_id, occurred_at);
create index submissions_task_lookup on app.submissions (company_id, task_id, version desc);
create index task_corrections_open_lookup
  on app.task_corrections (company_id, task_id, created_at) where status = 'open';
create index familiarity_employee_lookup
  on app.familiarity_evidence (company_id, employee_id, last_engaged_at desc);

create trigger execution_resources_touch_updated before update on app.execution_resources
  for each row execute function app.touch_updated_row();

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

  delete from app.effort_observations where company_id = p_company_id;
  delete from app.familiarity_evidence where company_id = p_company_id;
  delete from app.task_corrections where company_id = p_company_id;
  delete from app.task_reviews where company_id = p_company_id;
  delete from app.submission_files where company_id = p_company_id;
  delete from app.submissions where company_id = p_company_id;
  delete from app.task_events where company_id = p_company_id;
  delete from app.task_review_policies where company_id = p_company_id;
  delete from app.task_access_grants where company_id = p_company_id;
  delete from app.committed_schedule_blocks where company_id = p_company_id;
  delete from app.work_assignments where company_id = p_company_id;
  delete from app.employee_workload_state where company_id = p_company_id;
  delete from app.work_items where company_id = p_company_id;
  delete from app.plan_approval_uses where company_id = p_company_id;
  delete from app.plan_commitments where company_id = p_company_id;
  delete from app.plan_approval_decisions where company_id = p_company_id;
  delete from app.plan_approval_requirements where company_id = p_company_id;
  delete from app.employee_brief_audience_grants where company_id = p_company_id;
  delete from app.employee_brief_versions where company_id = p_company_id;
  delete from app.plan_changes where company_id = p_company_id;
  delete from app.plan_schedule_blocks where company_id = p_company_id;
  delete from app.plan_task_placements where company_id = p_company_id;
  delete from app.audit_events where company_id = p_company_id;
  delete from app.outbox_intents where company_id = p_company_id;
  delete from app.plans where company_id = p_company_id;
  delete from app.solver_runs where company_id = p_company_id;
  delete from app.planning_snapshot_constraints where company_id = p_company_id;
  delete from app.planning_snapshots where company_id = p_company_id;
  delete from app.constraint_source_evidence where company_id = p_company_id;
  delete from app.validated_constraints where company_id = p_company_id;
  delete from app.clarification_questions where company_id = p_company_id;
  delete from app.trace_steps where company_id = p_company_id;
  delete from app.candidate_contracts where company_id = p_company_id;
  delete from app.interpretation_runs where company_id = p_company_id;
  delete from app.retrieval_runs where company_id = p_company_id;
  delete from app.planning_request_sources where company_id = p_company_id;
  delete from app.planning_requests where company_id = p_company_id;
  delete from app.projects where company_id = p_company_id;
  delete from app.private_files where company_id = p_company_id;
  delete from app.source_access_grants where company_id = p_company_id;
  delete from app.source_excerpts where company_id = p_company_id;
  update app.source_records set current_version_id = null where company_id = p_company_id;
  delete from app.source_versions where company_id = p_company_id;
  delete from app.source_records where company_id = p_company_id;
  delete from app.invitations where company_id = p_company_id;
  delete from app.team_memberships where company_id = p_company_id;
  delete from app.teams where company_id = p_company_id;
  delete from app.execution_resources where company_id = p_company_id;
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
values ('20260926017000', 'employee_workflow');
