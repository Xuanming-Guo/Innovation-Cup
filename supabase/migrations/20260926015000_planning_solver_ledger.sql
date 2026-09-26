-- Immutable validated-constraint, planning-snapshot and solver-result ledger.

create table app.validated_constraints (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  request_id uuid not null,
  candidate_contract_id uuid not null,
  constraint_key text not null check (constraint_key ~ '^[a-z][a-z0-9_.:-]{0,127}$'),
  schema_version text not null check (schema_version = 'validated-constraint.v1'),
  strength text not null check (strength in ('hard', 'preferred')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  source_version_ids jsonb not null check (jsonb_typeof(source_version_ids) = 'array'),
  authority_refs jsonb not null check (jsonb_typeof(authority_refs) = 'array'),
  confidentiality text not null check (confidentiality in ('company', 'restricted')),
  negotiability text not null check (negotiability in ('locked', 'authorized', 'preferred')),
  confirmation text not null check (confirmation = 'confirmed'),
  constraint_digest bytea not null check (octet_length(constraint_digest) = 32),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, candidate_contract_id, constraint_key),
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id),
  foreign key (company_id, candidate_contract_id)
    references app.candidate_contracts(company_id, id),
  check (jsonb_array_length(authority_refs) > 0 or jsonb_array_length(source_version_ids) > 0),
  check (strength <> 'hard' or negotiability <> 'preferred'),
  check (strength <> 'preferred' or negotiability <> 'locked')
);

create table app.constraint_source_evidence (
  company_id uuid not null,
  constraint_id uuid not null,
  source_version_id uuid not null,
  created_at timestamptz not null default clock_timestamp(),
  primary key (company_id, constraint_id, source_version_id),
  foreign key (company_id, constraint_id)
    references app.validated_constraints(company_id, id) on delete cascade,
  foreign key (company_id, source_version_id)
    references app.source_versions(company_id, id)
);

create table app.planning_snapshots (
  id uuid primary key,
  company_id uuid not null,
  request_id uuid not null,
  candidate_contract_id uuid not null,
  schema_version text not null check (schema_version = 'planning-snapshot.v1'),
  base_company_revision bigint not null check (base_company_revision >= 0),
  horizon_start timestamptz not null,
  horizon_end timestamptz not null,
  slot_minutes integer not null check (slot_minutes between 5 and 240),
  source_manifest_digest bytea not null check (octet_length(source_manifest_digest) = 32),
  permission_revision text not null check (length(permission_revision) between 1 and 120),
  profile_revision text not null check (length(profile_revision) between 1 and 120),
  estimate_revision text not null check (length(estimate_revision) between 1 and 120),
  compiler_version text not null check (length(compiler_version) between 1 and 120),
  policy jsonb not null check (jsonb_typeof(policy) = 'object'),
  normalized_snapshot jsonb not null check (jsonb_typeof(normalized_snapshot) = 'object'),
  snapshot_digest bytea not null check (octet_length(snapshot_digest) = 32),
  frozen_at timestamptz not null,
  unique (company_id, id),
  unique (company_id, snapshot_digest),
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id),
  foreign key (company_id, candidate_contract_id)
    references app.candidate_contracts(company_id, id),
  check (horizon_end > horizon_start),
  check (
    extract(epoch from (horizon_end - horizon_start))::bigint % (slot_minutes * 60) = 0
  )
);

create table app.planning_snapshot_constraints (
  company_id uuid not null,
  snapshot_id uuid not null,
  constraint_id uuid not null,
  ordinal integer not null check (ordinal >= 0),
  primary key (company_id, snapshot_id, constraint_id),
  unique (company_id, snapshot_id, ordinal),
  foreign key (company_id, snapshot_id)
    references app.planning_snapshots(company_id, id) on delete cascade,
  foreign key (company_id, constraint_id)
    references app.validated_constraints(company_id, id)
);

create table app.solver_runs (
  id uuid primary key,
  company_id uuid not null,
  snapshot_id uuid not null,
  scope text not null check (scope in ('pinned_insertion', 'authorized_repair')),
  application_classification text not null check (application_classification in (
    'OPTIMAL_WITHIN_MODEL',
    'FEASIBLE',
    'INFEASIBLE_WITHIN_SCOPE',
    'UNKNOWN_OR_TIMEOUT',
    'INVALID_INPUT'
  )),
  raw_status text not null check (raw_status in ('sat', 'unsat', 'unknown', 'invalid')),
  termination text not null check (termination in (
    'completed', 'timeout', 'resource_limit', 'unknown', 'invalid'
  )),
  reason_unknown text null check (reason_unknown is null or length(reason_unknown) <= 500),
  model_digest bytea null check (model_digest is null or octet_length(model_digest) = 32),
  compiler_version text null check (compiler_version is null or length(compiler_version) <= 120),
  solver_version text not null check (length(solver_version) between 1 and 120),
  validator_version text null check (validator_version is null or length(validator_version) <= 120),
  timeout_ms integer not null check (timeout_ms > 0),
  resource_limit bigint not null check (resource_limit > 0),
  runtime_ms integer not null check (runtime_ms >= 0),
  objective_vector jsonb not null check (jsonb_typeof(objective_vector) = 'array'),
  diagnostic_constraint_keys jsonb not null
    check (jsonb_typeof(diagnostic_constraint_keys) = 'array'),
  validation_report jsonb null check (
    validation_report is null or jsonb_typeof(validation_report) = 'object'
  ),
  started_at timestamptz not null,
  completed_at timestamptz not null,
  unique (company_id, id),
  foreign key (company_id, snapshot_id)
    references app.planning_snapshots(company_id, id),
  check (completed_at >= started_at),
  check ((raw_status = 'unknown') = (reason_unknown is not null)),
  check ((raw_status = 'invalid') = (application_classification = 'INVALID_INPUT')),
  check ((raw_status = 'unsat') = (application_classification = 'INFEASIBLE_WITHIN_SCOPE')),
  check (raw_status <> 'sat' or validation_report is not null),
  check ((termination in ('timeout', 'resource_limit', 'unknown')) = (raw_status = 'unknown'))
);

create table app.plans (
  id uuid primary key,
  company_id uuid not null,
  request_id uuid not null,
  snapshot_id uuid not null,
  solver_run_id uuid not null,
  state text not null check (state = 'proposed'),
  classification text not null check (classification in ('OPTIMAL_WITHIN_MODEL', 'FEASIBLE')),
  proposal_digest bytea not null check (octet_length(proposal_digest) = 32),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, proposal_digest),
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id),
  foreign key (company_id, snapshot_id)
    references app.planning_snapshots(company_id, id),
  foreign key (company_id, solver_run_id)
    references app.solver_runs(company_id, id)
);

create table app.plan_task_placements (
  company_id uuid not null,
  plan_id uuid not null,
  task_id uuid not null,
  start_slot integer not null check (start_slot >= 0),
  end_slot integer not null check (end_slot > start_slot),
  owner_resource_id uuid null,
  primary key (company_id, plan_id, task_id),
  foreign key (company_id, plan_id)
    references app.plans(company_id, id) on delete cascade
);

create table app.plan_schedule_blocks (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  plan_id uuid not null,
  task_id uuid not null,
  resource_id uuid not null,
  start_slot integer not null check (start_slot >= 0),
  end_slot integer not null check (end_slot > start_slot),
  capacity_units integer not null check (capacity_units between 1 and 16),
  block_role text not null check (block_role in ('owner', 'participant', 'shared')),
  unique (company_id, id),
  unique (company_id, plan_id, task_id, resource_id, start_slot, block_role),
  foreign key (company_id, plan_id)
    references app.plans(company_id, id) on delete cascade
);

alter table app.trace_steps drop constraint trace_steps_step_type_check;
alter table app.trace_steps add constraint trace_steps_step_type_check check (step_type in (
  'request_loaded',
  'permission_checked',
  'source_retrieved',
  'projection_frozen',
  'model_called',
  'candidate_validated',
  'constraints_validated',
  'snapshot_frozen',
  'model_compiled',
  'solver_completed',
  'schedule_validated'
));

create or replace function app.can_read_planning_snapshot(
  p_company_id uuid,
  p_user_id uuid,
  p_snapshot_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1
    from app.planning_snapshots
    where company_id = p_company_id
      and id = p_snapshot_id
      and app.can_read_planning_request(company_id, p_user_id, request_id)
  )
$$;

create or replace function app.can_read_plan(
  p_company_id uuid,
  p_user_id uuid,
  p_plan_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1
    from app.plans
    where company_id = p_company_id
      and id = p_plan_id
      and app.can_read_planning_request(company_id, p_user_id, request_id)
  )
$$;

revoke execute on function app.can_read_planning_snapshot(uuid, uuid, uuid) from public;
revoke execute on function app.can_read_plan(uuid, uuid, uuid) from public;
grant execute on function app.can_read_planning_snapshot(uuid, uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.can_read_plan(uuid, uuid, uuid)
  to coordination_api, coordination_worker;

alter table app.validated_constraints enable row level security;
alter table app.constraint_source_evidence enable row level security;
alter table app.planning_snapshots enable row level security;
alter table app.planning_snapshot_constraints enable row level security;
alter table app.solver_runs enable row level security;
alter table app.plans enable row level security;
alter table app.plan_task_placements enable row level security;
alter table app.plan_schedule_blocks enable row level security;

create policy validated_constraints_manager_select on app.validated_constraints
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );
create policy validated_constraints_worker_insert on app.validated_constraints
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy constraint_source_evidence_manager_select on app.constraint_source_evidence
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and exists (
      select 1 from app.validated_constraints as constraint_record
      where constraint_record.company_id = constraint_source_evidence.company_id
        and constraint_record.id = constraint_source_evidence.constraint_id
    )
  );
create policy constraint_source_evidence_worker_insert on app.constraint_source_evidence
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and exists (
      select 1 from app.validated_constraints as constraint_record
      where constraint_record.company_id = constraint_source_evidence.company_id
        and constraint_record.id = constraint_source_evidence.constraint_id
    )
  );

create policy planning_snapshots_manager_select on app.planning_snapshots
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );
create policy planning_snapshots_worker_insert on app.planning_snapshots
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy planning_snapshot_constraints_manager_select
  on app.planning_snapshot_constraints
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_snapshot(company_id, app.current_actor_id(), snapshot_id)
  );
create policy planning_snapshot_constraints_worker_insert
  on app.planning_snapshot_constraints
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_snapshot(company_id, app.current_actor_id(), snapshot_id)
  );

create policy solver_runs_manager_select on app.solver_runs
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_snapshot(company_id, app.current_actor_id(), snapshot_id)
  );
create policy solver_runs_worker_insert on app.solver_runs
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_snapshot(company_id, app.current_actor_id(), snapshot_id)
  );

create policy plans_manager_select on app.plans
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );
create policy plans_worker_insert on app.plans
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
    and app.can_read_planning_snapshot(company_id, app.current_actor_id(), snapshot_id)
  );

create policy plan_task_placements_manager_select on app.plan_task_placements
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id)
  );
create policy plan_task_placements_worker_insert on app.plan_task_placements
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id)
  );

create policy plan_schedule_blocks_manager_select on app.plan_schedule_blocks
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id)
  );
create policy plan_schedule_blocks_worker_insert on app.plan_schedule_blocks
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_plan(company_id, app.current_actor_id(), plan_id)
  );

grant select on app.validated_constraints, app.constraint_source_evidence,
  app.planning_snapshots, app.planning_snapshot_constraints, app.solver_runs,
  app.plans, app.plan_task_placements, app.plan_schedule_blocks
  to coordination_api;
grant select, insert on app.validated_constraints, app.constraint_source_evidence,
  app.planning_snapshots, app.planning_snapshot_constraints, app.solver_runs,
  app.plans, app.plan_task_placements, app.plan_schedule_blocks
  to coordination_worker;

create index validated_constraints_request_lookup
  on app.validated_constraints (company_id, request_id, created_at);
create index planning_snapshots_request_lookup
  on app.planning_snapshots (company_id, request_id, frozen_at desc);
create index solver_runs_snapshot_lookup
  on app.solver_runs (company_id, snapshot_id, started_at);
create index plans_request_lookup on app.plans (company_id, request_id, created_at desc);
create index plan_schedule_blocks_resource_lookup
  on app.plan_schedule_blocks (company_id, resource_id, start_slot, end_slot);

insert into app_private.migration_contract (version, name)
values ('20260926015000', 'planning_solver_ledger');
