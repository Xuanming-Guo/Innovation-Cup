-- Exact proposal approvals and atomic plan commitment.

create extension if not exists btree_gist with schema extensions;

create table app.plan_changes (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  plan_id uuid not null,
  change_kind text not null check (change_kind in (
    'assignment', 'schedule', 'deadline', 'cross_team_displacement', 'disclosure'
  )),
  summary text not null check (length(btrim(summary)) between 1 and 1000),
  before_value jsonb null check (before_value is null or jsonb_typeof(before_value) = 'object'),
  after_value jsonb null check (after_value is null or jsonb_typeof(after_value) = 'object'),
  affected_team_id uuid null,
  supporting_constraint_keys jsonb not null default '[]'::jsonb
    check (jsonb_typeof(supporting_constraint_keys) = 'array'),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique nulls not distinct (company_id, plan_id, change_kind, affected_team_id, summary),
  foreign key (company_id, plan_id) references app.plans(company_id, id) on delete cascade,
  foreign key (company_id, affected_team_id) references app.teams(company_id, id)
);

create table app.employee_brief_versions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  plan_id uuid not null,
  version integer not null check (version > 0),
  brief_payload jsonb not null check (jsonb_typeof(brief_payload) = 'object'),
  audience_scope jsonb not null check (jsonb_typeof(audience_scope) = 'object'),
  brief_digest bytea not null check (octet_length(brief_digest) = 32),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, plan_id, version),
  unique (company_id, plan_id, brief_digest),
  foreign key (company_id, plan_id) references app.plans(company_id, id) on delete cascade
);

create table app.plan_approval_requirements (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  plan_id uuid not null,
  approval_domain text not null check (approval_domain in ('planning', 'disclosure')),
  requirement_kind text not null check (requirement_kind in (
    'plan_commit', 'deadline_change', 'cross_team_displacement', 'employee_brief_disclosure'
  )),
  authority_kind text not null check (authority_kind in (
    'company_manager', 'team_manager', 'company_admin'
  )),
  authority_team_id uuid null,
  artifact_digest bytea not null check (octet_length(artifact_digest) = 32),
  proposal_digest bytea not null check (octet_length(proposal_digest) = 32),
  snapshot_digest bytea not null check (octet_length(snapshot_digest) = 32),
  source_manifest_digest bytea not null check (octet_length(source_manifest_digest) = 32),
  base_company_revision bigint not null check (base_company_revision >= 0),
  policy_revision bigint not null check (policy_revision >= 0),
  policy_version text not null check (length(policy_version) between 1 and 120),
  reason text not null check (length(btrim(reason)) between 1 and 1000),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique nulls not distinct (
    company_id, plan_id, approval_domain, requirement_kind, authority_kind,
    authority_team_id, artifact_digest
  ),
  foreign key (company_id, plan_id) references app.plans(company_id, id) on delete cascade,
  foreign key (company_id, authority_team_id) references app.teams(company_id, id),
  check ((authority_kind = 'team_manager') = (authority_team_id is not null)),
  check (
    (approval_domain = 'disclosure') =
    (requirement_kind = 'employee_brief_disclosure')
  )
);

create table app.plan_approval_decisions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  plan_id uuid not null,
  requirement_id uuid not null,
  actor_membership_id uuid not null,
  decision text not null check (decision in ('approved', 'rejected')),
  explanation text null check (explanation is null or length(explanation) <= 2000),
  artifact_digest bytea not null check (octet_length(artifact_digest) = 32),
  proposal_digest bytea not null check (octet_length(proposal_digest) = 32),
  snapshot_digest bytea not null check (octet_length(snapshot_digest) = 32),
  source_manifest_digest bytea not null check (octet_length(source_manifest_digest) = 32),
  base_company_revision bigint not null check (base_company_revision >= 0),
  policy_revision bigint not null check (policy_revision >= 0),
  policy_version text not null check (length(policy_version) between 1 and 120),
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  command_digest bytea not null check (octet_length(command_digest) = 32),
  decided_at timestamptz not null default clock_timestamp(),
  expires_at timestamptz null,
  unique (company_id, id),
  unique (company_id, actor_membership_id, idempotency_key),
  foreign key (company_id, plan_id) references app.plans(company_id, id),
  foreign key (company_id, requirement_id)
    references app.plan_approval_requirements(company_id, id),
  foreign key (company_id, actor_membership_id)
    references app.company_memberships(company_id, id),
  check ((decision = 'approved') = (expires_at is not null)),
  check (expires_at is null or expires_at > decided_at)
);

create table app.plan_commitments (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  plan_id uuid not null,
  committed_by_membership_id uuid not null,
  proposal_digest bytea not null check (octet_length(proposal_digest) = 32),
  snapshot_digest bytea not null check (octet_length(snapshot_digest) = 32),
  source_manifest_digest bytea not null check (octet_length(source_manifest_digest) = 32),
  base_company_revision bigint not null check (base_company_revision >= 0),
  committed_company_revision bigint not null check (committed_company_revision > 0),
  policy_revision bigint not null check (policy_revision >= 0),
  policy_version text not null check (length(policy_version) between 1 and 120),
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  command_digest bytea not null check (octet_length(command_digest) = 32),
  correlation_id uuid not null,
  committed_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, plan_id),
  unique (company_id, committed_by_membership_id, idempotency_key),
  foreign key (company_id, plan_id) references app.plans(company_id, id),
  foreign key (company_id, committed_by_membership_id)
    references app.company_memberships(company_id, id)
);

create table app.plan_approval_uses (
  company_id uuid not null,
  commitment_id uuid not null,
  decision_id uuid not null,
  used_at timestamptz not null default clock_timestamp(),
  primary key (company_id, commitment_id, decision_id),
  unique (company_id, decision_id),
  foreign key (company_id, commitment_id)
    references app.plan_commitments(company_id, id) on delete cascade,
  foreign key (company_id, decision_id)
    references app.plan_approval_decisions(company_id, id)
);

create table app.work_items (
  company_id uuid not null,
  task_id uuid not null,
  project_id uuid null,
  source_request_id uuid not null,
  source_plan_id uuid not null,
  task_key text not null check (task_key ~ '^[a-z][a-z0-9_-]{0,63}$'),
  title text not null check (length(btrim(title)) between 1 and 160),
  scheduling_kind text not null check (scheduling_kind in (
    'flexible_active', 'review', 'fixed_attendance', 'passive_wait'
  )),
  status text not null default 'committed' check (status in (
    'committed', 'ready', 'in_progress', 'submitted', 'accepted', 'rework', 'cancelled'
  )),
  start_at timestamptz not null,
  finish_at timestamptz not null,
  owner_resource_id uuid null,
  committed_company_revision bigint not null check (committed_company_revision > 0),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  primary key (company_id, task_id),
  foreign key (company_id, project_id) references app.projects(company_id, id),
  foreign key (company_id, source_request_id)
    references app.planning_requests(company_id, id),
  foreign key (company_id, source_plan_id) references app.plans(company_id, id),
  check (finish_at > start_at)
);

create table app.work_assignments (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  task_id uuid not null,
  resource_id uuid not null,
  assignment_role text not null check (assignment_role in ('owner', 'participant', 'shared')),
  capacity_units integer not null check (capacity_units between 1 and 16),
  source_plan_id uuid not null,
  active boolean not null default true,
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, task_id, resource_id, assignment_role, source_plan_id),
  foreign key (company_id, task_id) references app.work_items(company_id, task_id),
  foreign key (company_id, source_plan_id) references app.plans(company_id, id)
);

create table app.committed_schedule_blocks (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  task_id uuid not null,
  resource_id uuid not null,
  source_plan_id uuid not null,
  start_at timestamptz not null,
  end_at timestamptz not null,
  time_range tstzrange generated always as (tstzrange(start_at, end_at, '[)')) stored,
  capacity_units integer not null check (capacity_units between 1 and 16),
  block_role text not null check (block_role in ('owner', 'participant', 'shared')),
  exclusive boolean not null,
  active boolean not null default true,
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, source_plan_id, task_id, resource_id, start_at, block_role),
  foreign key (company_id, task_id) references app.work_items(company_id, task_id),
  foreign key (company_id, source_plan_id) references app.plans(company_id, id),
  check (end_at > start_at),
  exclude using gist (
    company_id with =,
    resource_id with =,
    time_range with &&
  ) where (active and exclusive)
);

create table app.outbox_intents (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  intent_kind text not null check (intent_kind in (
    'plan.committed', 'employee_brief.publish', 'task.changed', 'approval.changed'
  )),
  aggregate_type text not null check (length(aggregate_type) between 1 and 80),
  aggregate_id uuid not null,
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  correlation_id uuid not null,
  available_at timestamptz not null default clock_timestamp(),
  processed_at timestamptz null,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  last_error text null check (last_error is null or length(last_error) <= 2000),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id)
);

create table app.audit_events (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  actor_membership_id uuid null,
  event_type text not null check (length(event_type) between 1 and 120),
  aggregate_type text not null check (length(aggregate_type) between 1 and 80),
  aggregate_id uuid not null,
  outcome text not null check (outcome in ('accepted', 'rejected', 'committed', 'stale')),
  policy_revision bigint not null check (policy_revision >= 0),
  input_digest bytea null check (input_digest is null or octet_length(input_digest) = 32),
  output_digest bytea null check (output_digest is null or octet_length(output_digest) = 32),
  details jsonb not null check (jsonb_typeof(details) = 'object'),
  correlation_id uuid not null,
  occurred_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  foreign key (company_id, actor_membership_id)
    references app.company_memberships(company_id, id)
);

create index plan_changes_plan_lookup on app.plan_changes (company_id, plan_id, created_at);
create index plan_requirements_plan_lookup
  on app.plan_approval_requirements (company_id, plan_id, approval_domain);
create index plan_decisions_requirement_lookup
  on app.plan_approval_decisions (company_id, requirement_id, decided_at desc);
create index work_items_status_lookup on app.work_items (company_id, status, start_at);
create index committed_schedule_resource_lookup
  on app.committed_schedule_blocks (company_id, resource_id, start_at, end_at)
  where active;
create index outbox_ready_lookup
  on app.outbox_intents (available_at, created_at) where processed_at is null;
create index audit_aggregate_lookup
  on app.audit_events (company_id, aggregate_type, aggregate_id, occurred_at desc);

create or replace function app.actor_satisfies_plan_requirement(
  p_company_id uuid,
  p_user_id uuid,
  p_requirement_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1
    from app.plan_approval_requirements as requirement
    join app.company_memberships as membership
      on membership.company_id = requirement.company_id
     and membership.user_id = p_user_id
     and membership.membership_status = 'active'
    left join app.employee_profiles as employee
      on employee.company_id = membership.company_id
     and employee.membership_id = membership.id
     and employee.status = 'active'
    where requirement.company_id = p_company_id
      and requirement.id = p_requirement_id
      and (
        (requirement.authority_kind = 'company_admin'
          and membership.administrative_role = 'company_admin')
        or (requirement.authority_kind = 'company_manager'
          and membership.administrative_role in ('manager', 'company_admin'))
        or (requirement.authority_kind = 'team_manager' and (
          membership.administrative_role = 'company_admin'
          or exists (
            select 1 from app.team_memberships as team_membership
            where team_membership.company_id = requirement.company_id
              and team_membership.team_id = requirement.authority_team_id
              and team_membership.employee_id = employee.id
              and team_membership.team_role = 'manager'
              and team_membership.valid_from <= clock_timestamp()
              and (team_membership.valid_to is null or team_membership.valid_to > clock_timestamp())
          )
        ))
      )
  )
$$;

create or replace function app.require_employee_brief_approval()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_binding record;
begin
  select plan.proposal_digest, snapshot.snapshot_digest,
         snapshot.source_manifest_digest, snapshot.base_company_revision,
         snapshot.policy ->> 'policy_version' as policy_version,
         company.policy_revision
  into v_binding
  from app.plans as plan
  join app.planning_snapshots as snapshot
    on snapshot.company_id = plan.company_id and snapshot.id = plan.snapshot_id
  join app.companies as company on company.id = plan.company_id
  where plan.company_id = new.company_id and plan.id = new.plan_id;

  insert into app.plan_approval_requirements (
    company_id, plan_id, approval_domain, requirement_kind, authority_kind,
    artifact_digest, proposal_digest, snapshot_digest, source_manifest_digest,
    base_company_revision, policy_revision, policy_version, reason
  ) values (
    new.company_id, new.plan_id, 'disclosure', 'employee_brief_disclosure',
    'company_manager', new.brief_digest, v_binding.proposal_digest,
    v_binding.snapshot_digest, v_binding.source_manifest_digest,
    v_binding.base_company_revision, v_binding.policy_revision,
    v_binding.policy_version,
    'Approve the exact employee brief content and audience separately from the plan.'
  ) on conflict do nothing;

  insert into app.plan_changes (
    company_id, plan_id, change_kind, summary, after_value,
    supporting_constraint_keys
  ) values (
    new.company_id, new.plan_id, 'disclosure',
    'Employee-facing brief and audience require separate disclosure approval.',
    jsonb_build_object('brief_version_id', new.id, 'audience_scope', new.audience_scope),
    '[]'::jsonb
  ) on conflict do nothing;
  return new;
end
$$;

create or replace function app.plan_sources_are_current(p_company_id uuid, p_plan_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select not exists (
    select 1
    from app.plans as plan
    join app.planning_request_sources as selected
      on selected.company_id = plan.company_id and selected.request_id = plan.request_id
    join app.source_records as source
      on source.company_id = selected.company_id and source.id = selected.source_id
    join app.source_versions as version
      on version.company_id = selected.company_id and version.id = selected.source_version_id
    where plan.company_id = p_company_id
      and plan.id = p_plan_id
      and (
        source.status <> 'active'
        or source.authority_status <> 'authoritative'
        or source.current_version_id <> selected.source_version_id
        or (version.expires_at is not null and version.expires_at <= clock_timestamp())
      )
  )
$$;

create or replace function app.record_plan_approval_decision(
  p_company_id uuid,
  p_plan_id uuid,
  p_requirement_id uuid,
  p_decision text,
  p_explanation text,
  p_artifact_digest bytea,
  p_proposal_digest bytea,
  p_snapshot_digest bytea,
  p_source_manifest_digest bytea,
  p_base_company_revision bigint,
  p_policy_revision bigint,
  p_policy_version text,
  p_idempotency_key text,
  p_command_digest bytea,
  p_correlation_id uuid
)
returns table (decision_id uuid, recorded_decision text, replayed boolean)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_membership_id uuid;
  v_existing app.plan_approval_decisions%rowtype;
  v_requirement app.plan_approval_requirements%rowtype;
  v_company app.companies%rowtype;
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id() then
    raise exception using errcode = '42501', message = 'request_context_invalid';
  end if;
  if p_decision not in ('approved', 'rejected') then
    raise exception using errcode = '22023', message = 'decision_invalid';
  end if;

  select id into v_membership_id
  from app.company_memberships
  where company_id = p_company_id and user_id = app.current_actor_id()
    and membership_status = 'active';
  if v_membership_id is null then
    raise exception using errcode = '42501', message = 'active_membership_required';
  end if;

  select * into v_existing
  from app.plan_approval_decisions
  where company_id = p_company_id
    and actor_membership_id = v_membership_id
    and idempotency_key = p_idempotency_key;
  if found then
    if v_existing.command_digest <> p_command_digest then
      raise exception using errcode = '23505', message = 'idempotency_key_reused';
    end if;
    return query select v_existing.id, v_existing.decision, true;
    return;
  end if;

  select * into v_company from app.companies
  where id = p_company_id and status = 'active' for share;
  select * into v_requirement from app.plan_approval_requirements
  where company_id = p_company_id and id = p_requirement_id and plan_id = p_plan_id;
  if not found then
    raise exception using errcode = 'P0002', message = 'requirement_not_found';
  end if;
  if v_company.planning_revision <> p_base_company_revision
     or v_company.policy_revision <> p_policy_revision
     or v_requirement.artifact_digest <> p_artifact_digest
     or v_requirement.proposal_digest <> p_proposal_digest
     or v_requirement.snapshot_digest <> p_snapshot_digest
     or v_requirement.source_manifest_digest <> p_source_manifest_digest
     or v_requirement.base_company_revision <> p_base_company_revision
     or v_requirement.policy_revision <> p_policy_revision
     or v_requirement.policy_version <> p_policy_version
     or not app.plan_sources_are_current(p_company_id, p_plan_id) then
    raise exception using errcode = '40001', message = 'approval_binding_stale';
  end if;
  if not app.actor_satisfies_plan_requirement(
    p_company_id, app.current_actor_id(), p_requirement_id
  ) then
    raise exception using errcode = '42501', message = 'approval_authority_required';
  end if;

  insert into app.plan_approval_decisions (
    company_id, plan_id, requirement_id, actor_membership_id, decision, explanation,
    artifact_digest, proposal_digest, snapshot_digest, source_manifest_digest,
    base_company_revision, policy_revision, policy_version, idempotency_key,
    command_digest, expires_at
  ) values (
    p_company_id, p_plan_id, p_requirement_id, v_membership_id, p_decision,
    nullif(btrim(p_explanation), ''), p_artifact_digest, p_proposal_digest,
    p_snapshot_digest, p_source_manifest_digest, p_base_company_revision,
    p_policy_revision, p_policy_version, p_idempotency_key, p_command_digest,
    case when p_decision = 'approved' then clock_timestamp() + interval '24 hours' end
  ) returning id into decision_id;
  recorded_decision := p_decision;
  replayed := false;

  insert into app.audit_events (
    company_id, actor_membership_id, event_type, aggregate_type, aggregate_id,
    outcome, policy_revision, input_digest, output_digest, details, correlation_id
  ) values (
    p_company_id, v_membership_id, 'plan.approval.' || p_decision, 'plan', p_plan_id,
    case when p_decision = 'approved' then 'accepted' else 'rejected' end,
    p_policy_revision, p_command_digest, p_artifact_digest,
    jsonb_build_object('requirement_id', p_requirement_id, 'policy_version', p_policy_version),
    p_correlation_id
  );
  return next;
end
$$;

create or replace function app.commit_approved_plan(
  p_company_id uuid,
  p_plan_id uuid,
  p_proposal_digest bytea,
  p_snapshot_digest bytea,
  p_source_manifest_digest bytea,
  p_base_company_revision bigint,
  p_policy_revision bigint,
  p_policy_version text,
  p_idempotency_key text,
  p_command_digest bytea,
  p_correlation_id uuid
)
returns table (
  commitment_id uuid,
  commit_status text,
  committed_revision bigint,
  replayed boolean
)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_membership_id uuid;
  v_existing app.plan_commitments%rowtype;
  v_plan record;
  v_company app.companies%rowtype;
  v_missing integer;
  v_new_revision bigint;
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id() then
    raise exception using errcode = '42501', message = 'request_context_invalid';
  end if;
  select id into v_membership_id
  from app.company_memberships
  where company_id = p_company_id and user_id = app.current_actor_id()
    and membership_status = 'active'
    and administrative_role in ('manager', 'company_admin');
  if v_membership_id is null then
    raise exception using errcode = '42501', message = 'manager_authority_required';
  end if;

  select * into v_existing from app.plan_commitments
  where company_id = p_company_id
    and committed_by_membership_id = v_membership_id
    and idempotency_key = p_idempotency_key;
  if found then
    if v_existing.command_digest <> p_command_digest then
      raise exception using errcode = '23505', message = 'idempotency_key_reused';
    end if;
    return query select v_existing.id, 'committed'::text,
      v_existing.committed_company_revision, true;
    return;
  end if;

  select * into v_company from app.companies
  where id = p_company_id and status = 'active' for update;
  if v_company.planning_revision <> p_base_company_revision
     or v_company.policy_revision <> p_policy_revision then
    raise exception using errcode = '40001', message = 'plan_base_revision_stale';
  end if;

  select plan.id, plan.request_id, plan.proposal_digest,
         snapshot.id as snapshot_id, snapshot.snapshot_digest,
         snapshot.source_manifest_digest, snapshot.base_company_revision,
         snapshot.horizon_start, snapshot.slot_minutes,
         snapshot.policy ->> 'policy_version' as policy_version,
         request.project_id, solver.validation_report
  into v_plan
  from app.plans as plan
  join app.planning_snapshots as snapshot
    on snapshot.company_id = plan.company_id and snapshot.id = plan.snapshot_id
  join app.planning_requests as request
    on request.company_id = plan.company_id and request.id = plan.request_id
  join app.solver_runs as solver
    on solver.company_id = plan.company_id and solver.id = plan.solver_run_id
  where plan.company_id = p_company_id and plan.id = p_plan_id;
  if not found then
    raise exception using errcode = 'P0002', message = 'plan_not_found';
  end if;
  if v_plan.proposal_digest <> p_proposal_digest
     or v_plan.snapshot_digest <> p_snapshot_digest
     or v_plan.source_manifest_digest <> p_source_manifest_digest
     or v_plan.base_company_revision <> p_base_company_revision
     or v_plan.policy_version <> p_policy_version
     or coalesce((v_plan.validation_report ->> 'valid')::boolean, false) is not true
     or not app.plan_sources_are_current(p_company_id, p_plan_id) then
    raise exception using errcode = '40001', message = 'plan_binding_stale';
  end if;

  select count(*) into v_missing
  from app.plan_approval_requirements as requirement
  where requirement.company_id = p_company_id
    and requirement.plan_id = p_plan_id
    and requirement.approval_domain = 'planning'
    and not exists (
      select 1
      from app.plan_approval_decisions as decision
      join app.company_memberships as approver
        on approver.company_id = decision.company_id
       and approver.id = decision.actor_membership_id
       and approver.membership_status = 'active'
      where decision.company_id = requirement.company_id
        and decision.requirement_id = requirement.id
        and decision.decision = 'approved'
        and decision.expires_at > clock_timestamp()
        and decision.artifact_digest = requirement.artifact_digest
        and decision.proposal_digest = p_proposal_digest
        and decision.snapshot_digest = p_snapshot_digest
        and decision.source_manifest_digest = p_source_manifest_digest
        and decision.base_company_revision = p_base_company_revision
        and decision.policy_revision = p_policy_revision
        and decision.policy_version = p_policy_version
        and app.actor_satisfies_plan_requirement(
          p_company_id, approver.user_id, requirement.id
        )
        and not exists (
          select 1 from app.plan_approval_decisions as later
          where later.company_id = decision.company_id
            and later.requirement_id = decision.requirement_id
            and later.decided_at > decision.decided_at
        )
    );
  if v_missing > 0 or not exists (
    select 1 from app.plan_approval_requirements
    where company_id = p_company_id and plan_id = p_plan_id
      and approval_domain = 'planning'
  ) then
    raise exception using errcode = '42501', message = 'plan_approval_incomplete';
  end if;

  v_new_revision := p_base_company_revision + 1;
  insert into app.plan_commitments (
    company_id, plan_id, committed_by_membership_id, proposal_digest,
    snapshot_digest, source_manifest_digest, base_company_revision,
    committed_company_revision, policy_revision, policy_version,
    idempotency_key, command_digest, correlation_id
  ) values (
    p_company_id, p_plan_id, v_membership_id, p_proposal_digest,
    p_snapshot_digest, p_source_manifest_digest, p_base_company_revision,
    v_new_revision, p_policy_revision, p_policy_version, p_idempotency_key,
    p_command_digest, p_correlation_id
  ) returning id into commitment_id;

  insert into app.work_items (
    company_id, task_id, project_id, source_request_id, source_plan_id,
    task_key, title, scheduling_kind, start_at, finish_at,
    owner_resource_id, committed_company_revision
  )
  select p_company_id, placement.task_id, v_plan.project_id, v_plan.request_id, p_plan_id,
    definition.payload ->> 'task_key', definition.payload ->> 'title',
    definition.payload ->> 'scheduling_kind',
    v_plan.horizon_start + (placement.start_slot * v_plan.slot_minutes) * interval '1 minute',
    v_plan.horizon_start + (placement.end_slot * v_plan.slot_minutes) * interval '1 minute',
    placement.owner_resource_id, v_new_revision
  from app.plan_task_placements as placement
  join app.validated_constraints as definition
    on definition.company_id = placement.company_id
   and definition.request_id = v_plan.request_id
   and definition.payload ->> 'family' = 'task_definition'
   and definition.payload ->> 'task_id' = placement.task_id::text
  where placement.company_id = p_company_id and placement.plan_id = p_plan_id;

  if (select count(*) from app.work_items
      where company_id = p_company_id and source_plan_id = p_plan_id)
     <> (select count(*) from app.plan_task_placements
         where company_id = p_company_id and plan_id = p_plan_id) then
    raise exception using errcode = '23514', message = 'committed_candidate_mismatch';
  end if;

  insert into app.work_assignments (
    company_id, task_id, resource_id, assignment_role, capacity_units, source_plan_id
  )
  select company_id, task_id, resource_id, block_role, max(capacity_units), plan_id
  from app.plan_schedule_blocks
  where company_id = p_company_id and plan_id = p_plan_id
  group by company_id, task_id, resource_id, block_role, plan_id;

  insert into app.committed_schedule_blocks (
    company_id, task_id, resource_id, source_plan_id, start_at, end_at,
    capacity_units, block_role, exclusive
  )
  select block.company_id, block.task_id, block.resource_id, block.plan_id,
    v_plan.horizon_start + (block.start_slot * v_plan.slot_minutes) * interval '1 minute',
    v_plan.horizon_start + (block.end_slot * v_plan.slot_minutes) * interval '1 minute',
    block.capacity_units, block.block_role,
    block.block_role in ('owner', 'participant')
      and item.scheduling_kind <> 'passive_wait'
  from app.plan_schedule_blocks as block
  join app.work_items as item
    on item.company_id = block.company_id and item.task_id = block.task_id
  where block.company_id = p_company_id and block.plan_id = p_plan_id;

  insert into app.plan_approval_uses (company_id, commitment_id, decision_id)
  select p_company_id, commitment_id, decision.id
  from app.plan_approval_requirements as requirement
  join lateral (
    select candidate.id
    from app.plan_approval_decisions as candidate
    where candidate.company_id = requirement.company_id
      and candidate.requirement_id = requirement.id
      and candidate.decision = 'approved'
    order by candidate.decided_at desc
    limit 1
  ) as decision on true
  where requirement.company_id = p_company_id
    and requirement.plan_id = p_plan_id
    and requirement.approval_domain = 'planning';

  insert into app.outbox_intents (
    company_id, intent_kind, aggregate_type, aggregate_id, payload, correlation_id
  ) values (
    p_company_id, 'plan.committed', 'plan', p_plan_id,
    jsonb_build_object('commitment_id', commitment_id, 'company_revision', v_new_revision),
    p_correlation_id
  );

  insert into app.audit_events (
    company_id, actor_membership_id, event_type, aggregate_type, aggregate_id,
    outcome, policy_revision, input_digest, output_digest, details, correlation_id
  ) values (
    p_company_id, v_membership_id, 'plan.committed', 'plan', p_plan_id,
    'committed', p_policy_revision, p_command_digest, p_proposal_digest,
    jsonb_build_object(
      'commitment_id', commitment_id,
      'base_company_revision', p_base_company_revision,
      'committed_company_revision', v_new_revision,
      'policy_version', p_policy_version
    ), p_correlation_id
  );

  update app.companies
  set planning_revision = v_new_revision
  where id = p_company_id;

  commit_status := 'committed';
  committed_revision := v_new_revision;
  replayed := false;
  return next;
end
$$;

revoke execute on function app.actor_satisfies_plan_requirement(uuid, uuid, uuid) from public;
revoke execute on function app.require_employee_brief_approval() from public;
revoke execute on function app.plan_sources_are_current(uuid, uuid) from public;
revoke execute on function app.record_plan_approval_decision(
  uuid, uuid, uuid, text, text, bytea, bytea, bytea, bytea, bigint, bigint,
  text, text, bytea, uuid
) from public;
revoke execute on function app.commit_approved_plan(
  uuid, uuid, bytea, bytea, bytea, bigint, bigint, text, text, bytea, uuid
) from public;
grant execute on function app.actor_satisfies_plan_requirement(uuid, uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.require_employee_brief_approval() to coordination_worker;
grant execute on function app.plan_sources_are_current(uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.record_plan_approval_decision(
  uuid, uuid, uuid, text, text, bytea, bytea, bytea, bytea, bigint, bigint,
  text, text, bytea, uuid
) to coordination_api;
grant execute on function app.commit_approved_plan(
  uuid, uuid, bytea, bytea, bytea, bigint, bigint, text, text, bytea, uuid
) to coordination_api;

alter table app.plan_changes enable row level security;
alter table app.employee_brief_versions enable row level security;
alter table app.plan_approval_requirements enable row level security;
alter table app.plan_approval_decisions enable row level security;
alter table app.plan_commitments enable row level security;
alter table app.plan_approval_uses enable row level security;
alter table app.work_items enable row level security;
alter table app.work_assignments enable row level security;
alter table app.committed_schedule_blocks enable row level security;
alter table app.outbox_intents enable row level security;
alter table app.audit_events enable row level security;

create policy plan_changes_manager_select on app.plan_changes
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id));
create policy plan_changes_worker_insert on app.plan_changes
  for insert to coordination_worker
  with check (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id));
create policy employee_briefs_manager_select on app.employee_brief_versions
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id));
create policy employee_briefs_worker_insert on app.employee_brief_versions
  for insert to coordination_worker
  with check (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id));
create policy plan_requirements_manager_select on app.plan_approval_requirements
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id));
create policy plan_requirements_worker_insert on app.plan_approval_requirements
  for insert to coordination_worker
  with check (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id));
create policy plan_decisions_manager_select on app.plan_approval_decisions
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id));
create policy plan_commitments_manager_select on app.plan_commitments
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id));
create policy plan_approval_uses_manager_select on app.plan_approval_uses
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id());
create policy work_items_company_select on app.work_items
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.has_active_membership(company_id, app.current_actor_id()));
create policy work_assignments_company_select on app.work_assignments
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.has_active_membership(company_id, app.current_actor_id()));
create policy committed_schedule_company_select on app.committed_schedule_blocks
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.has_active_membership(company_id, app.current_actor_id()));
create policy outbox_worker_select on app.outbox_intents
  for select to coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id());
create policy audit_manager_select on app.audit_events
  for select to coordination_api, coordination_worker
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_manage_planning(company_id, app.current_actor_id()));

grant select on app.plan_changes, app.employee_brief_versions,
  app.plan_approval_requirements, app.plan_approval_decisions, app.plan_commitments,
  app.plan_approval_uses, app.work_items, app.work_assignments,
  app.committed_schedule_blocks, app.audit_events to coordination_api, coordination_worker;
grant select on app.outbox_intents to coordination_worker;
grant insert on app.plan_changes, app.employee_brief_versions,
  app.plan_approval_requirements to coordination_worker;

create trigger work_items_touch_updated before update on app.work_items
  for each row execute function app.touch_updated_row();
create trigger employee_brief_requires_disclosure_approval
  after insert on app.employee_brief_versions
  for each row execute function app.require_employee_brief_approval();

insert into app_private.migration_contract (version, name)
values ('20260926016000', 'plan_approval_commit');
