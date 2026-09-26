begin;
select plan(12);

select has_table('app', 'validated_constraints', 'validated constraint ledger exists');
select has_table('app', 'planning_snapshots', 'immutable planning snapshots exist');
select has_table('app', 'solver_runs', 'solver run ledger exists');
select has_table('app', 'plans', 'validated plan proposals exist');
select has_table('app', 'plan_task_placements', 'plan placements exist');
select has_table('app', 'plan_schedule_blocks', 'concrete schedule blocks exist');

insert into auth.users (id, instance_id, aud, role, email, encrypted_password, created_at, updated_at)
values
  (
    '44444444-aaaa-4aaa-8aaa-aaaaaaaaaaa4',
    '00000000-0000-0000-0000-000000000000',
    'authenticated', 'authenticated', 'solver-a@example.invalid',
    extensions.crypt('local-test-only', extensions.gen_salt('bf')),
    clock_timestamp(), clock_timestamp()
  ),
  (
    '55555555-bbbb-4bbb-8bbb-bbbbbbbbbbb5',
    '00000000-0000-0000-0000-000000000000',
    'authenticated', 'authenticated', 'solver-b@example.invalid',
    extensions.crypt('local-test-only', extensions.gen_salt('bf')),
    clock_timestamp(), clock_timestamp()
  );

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values
  (
    '44444444-0000-4000-8000-000000000044',
    '11111111-1111-4111-8111-111111111111',
    '44444444-aaaa-4aaa-8aaa-aaaaaaaaaaa4',
    'active', 'manager', clock_timestamp()
  ),
  (
    '55555555-0000-4000-8000-000000000055',
    '22222222-2222-4222-8222-222222222222',
    '55555555-bbbb-4bbb-8bbb-bbbbbbbbbbb5',
    'active', 'manager', clock_timestamp()
  );

insert into app.planning_requests (
  id, company_id, requester_membership_id, original_prompt, idempotency_key, request_digest
) values (
  '44444444-4000-4000-8000-000000000044',
  '11111111-1111-4111-8111-111111111111',
  '44444444-0000-4000-8000-000000000044',
  'Create a finite schedule.', 'solver-fixture-key-a', decode(repeat('41', 32), 'hex')
);

insert into app.retrieval_runs (
  id, company_id, request_id, actor_membership_id, purpose, allowed_scope,
  selected_manifest, omitted_manifest, missing_manifest, projection_digest,
  projection_characters, status, started_at, completed_at
) values (
  '44444444-5000-4000-8000-000000000044',
  '11111111-1111-4111-8111-111111111111',
  '44444444-4000-4000-8000-000000000044',
  '44444444-0000-4000-8000-000000000044',
  'solver-test', '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
  decode(repeat('42', 32), 'hex'), 20, 'complete', clock_timestamp(), clock_timestamp()
);

insert into app.interpretation_runs (
  id, company_id, request_id, retrieval_run_id, model_id, sdk_version,
  prompt_version, schema_version, safety_profile, configuration, status,
  outcome, started_at, completed_at
) values (
  '44444444-6000-4000-8000-000000000044',
  '11111111-1111-4111-8111-111111111111',
  '44444444-4000-4000-8000-000000000044',
  '44444444-5000-4000-8000-000000000044',
  'fixture', '2.23.0', 'interpretation-v1', 'candidate-task-contract.v1',
  'provider-default-no-tools-v1', '{}'::jsonb, 'completed', 'admitted',
  clock_timestamp(), clock_timestamp()
);

insert into app.candidate_contracts (
  id, company_id, request_id, interpretation_run_id, contract_json,
  contract_digest, admission_status, validation_issues
) values (
  '44444444-7000-4000-8000-000000000044',
  '11111111-1111-4111-8111-111111111111',
  '44444444-4000-4000-8000-000000000044',
  '44444444-6000-4000-8000-000000000044',
  '{"schema_version":"candidate-task-contract.v1"}'::jsonb,
  decode(repeat('43', 32), 'hex'), 'admitted', '[]'::jsonb
);

create temporary table solver_test_results (
  label text primary key,
  observed text not null
) on commit drop;
grant insert, select on table solver_test_results to coordination_api, coordination_worker;

set local role coordination_worker;
select set_config('app.actor_id', '44444444-aaaa-4aaa-8aaa-aaaaaaaaaaa4', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:solver-worker', true);

insert into app.validated_constraints (
  id, company_id, request_id, candidate_contract_id, constraint_key,
  schema_version, strength, payload, source_version_ids, authority_refs,
  confidentiality, negotiability, confirmation, constraint_digest
) values (
  '44444444-8000-4000-8000-000000000044',
  '11111111-1111-4111-8111-111111111111',
  '44444444-4000-4000-8000-000000000044',
  '44444444-7000-4000-8000-000000000044',
  'fixture.task', 'validated-constraint.v1', 'hard',
  '{"family":"task_definition"}'::jsonb, '[]'::jsonb, '["manager:test"]'::jsonb,
  'company', 'locked', 'confirmed', decode(repeat('44', 32), 'hex')
);

insert into app.planning_snapshots (
  id, company_id, request_id, candidate_contract_id, schema_version,
  base_company_revision, horizon_start, horizon_end, slot_minutes,
  source_manifest_digest, permission_revision, profile_revision,
  estimate_revision, compiler_version, policy, normalized_snapshot,
  snapshot_digest, frozen_at
) values (
  '44444444-9000-4000-8000-000000000044',
  '11111111-1111-4111-8111-111111111111',
  '44444444-4000-4000-8000-000000000044',
  '44444444-7000-4000-8000-000000000044',
  'planning-snapshot.v1', 0, '2026-09-28 08:00:00+00', '2026-09-28 09:00:00+00', 15,
  decode(repeat('45', 32), 'hex'), 'permissions:1', 'profiles:1', 'estimates:1',
  'coordination-z3-compiler.v1', '{}'::jsonb, '{}'::jsonb,
  decode(repeat('46', 32), 'hex'), clock_timestamp()
);

insert into app.planning_snapshot_constraints (
  company_id, snapshot_id, constraint_id, ordinal
) values (
  '11111111-1111-4111-8111-111111111111',
  '44444444-9000-4000-8000-000000000044',
  '44444444-8000-4000-8000-000000000044', 0
);

insert into app.solver_runs (
  id, company_id, snapshot_id, scope, application_classification,
  raw_status, termination, solver_version, timeout_ms, resource_limit,
  runtime_ms, objective_vector, diagnostic_constraint_keys,
  started_at, completed_at
) values (
  '44444444-a000-4000-8000-000000000044',
  '11111111-1111-4111-8111-111111111111',
  '44444444-9000-4000-8000-000000000044',
  'pinned_insertion', 'INFEASIBLE_WITHIN_SCOPE', 'unsat', 'completed',
  '5.1.0.0', 5000, 10000000, 8, '[]'::jsonb, '["fixture.task"]'::jsonb,
  clock_timestamp(), clock_timestamp()
);

insert into app.solver_runs (
  id, company_id, snapshot_id, scope, application_classification,
  raw_status, termination, model_digest, compiler_version, solver_version,
  validator_version, timeout_ms, resource_limit, runtime_ms, objective_vector,
  diagnostic_constraint_keys, validation_report, started_at, completed_at
) values (
  '44444444-a000-4000-8000-000000000045',
  '11111111-1111-4111-8111-111111111111',
  '44444444-9000-4000-8000-000000000044',
  'authorized_repair', 'FEASIBLE', 'sat', 'completed', decode(repeat('47', 32), 'hex'),
  'coordination-z3-compiler.v1', '5.1.0.0', 'coordination-schedule-validator.v1',
  5000, 10000000, 12, '[{"name":"owner_changes","value":0}]'::jsonb,
  '[]'::jsonb, '{"valid":true}'::jsonb, clock_timestamp(), clock_timestamp()
);

insert into app.plans (
  id, company_id, request_id, snapshot_id, solver_run_id,
  state, classification, proposal_digest
) values (
  '44444444-b000-4000-8000-000000000044',
  '11111111-1111-4111-8111-111111111111',
  '44444444-4000-4000-8000-000000000044',
  '44444444-9000-4000-8000-000000000044',
  '44444444-a000-4000-8000-000000000045',
  'proposed', 'FEASIBLE', decode(repeat('48', 32), 'hex')
);

insert into app.plan_task_placements (
  company_id, plan_id, task_id, start_slot, end_slot, owner_resource_id
) values (
  '11111111-1111-4111-8111-111111111111',
  '44444444-b000-4000-8000-000000000044',
  '44444444-c000-4000-8000-000000000044', 0, 2,
  '44444444-d000-4000-8000-000000000044'
);

insert into app.plan_schedule_blocks (
  company_id, plan_id, task_id, resource_id, start_slot, end_slot,
  capacity_units, block_role
) values (
  '11111111-1111-4111-8111-111111111111',
  '44444444-b000-4000-8000-000000000044',
  '44444444-c000-4000-8000-000000000044',
  '44444444-d000-4000-8000-000000000044', 0, 2, 1, 'owner'
);

insert into solver_test_results values
  ('worker-snapshot-count', (select count(*)::text from app.planning_snapshots)),
  ('worker-plan-count', (select count(*)::text from app.plans));

do $$
begin
  begin
    update app.planning_snapshots
    set compiler_version = 'forged'
    where id = '44444444-9000-4000-8000-000000000044';
    insert into solver_test_results values ('worker-update-denied', 'false');
  exception when insufficient_privilege then
    insert into solver_test_results values ('worker-update-denied', 'true');
  end;
end
$$;
reset role;

set local role coordination_api;
select set_config('app.actor_id', '44444444-aaaa-4aaa-8aaa-aaaaaaaaaaa4', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:solver-manager', true);
insert into solver_test_results values
  ('manager-visible-count', (select count(*)::text from app.solver_runs));
do $$
begin
  begin
    insert into app.solver_runs (
      id, company_id, snapshot_id, scope, application_classification,
      raw_status, termination, solver_version, timeout_ms, resource_limit,
      runtime_ms, objective_vector, diagnostic_constraint_keys,
      started_at, completed_at
    ) values (
      gen_random_uuid(), '11111111-1111-4111-8111-111111111111',
      '44444444-9000-4000-8000-000000000044', 'pinned_insertion',
      'UNKNOWN_OR_TIMEOUT', 'unknown', 'timeout', 'forged', 1, 1, 0,
      '[]'::jsonb, '[]'::jsonb, clock_timestamp(), clock_timestamp()
    );
    insert into solver_test_results values ('api-insert-denied', 'false');
  exception when insufficient_privilege then
    insert into solver_test_results values ('api-insert-denied', 'true');
  end;
end
$$;
reset role;

set local role coordination_api;
select set_config('app.actor_id', '55555555-bbbb-4bbb-8bbb-bbbbbbbbbbb5', true);
select set_config('app.company_id', '22222222-2222-4222-8222-222222222222', true);
select set_config('app.purpose', 'test:solver-cross-tenant', true);
insert into solver_test_results values
  ('cross-tenant-count', (select count(*)::text from app.planning_snapshots));
reset role;

select is(
  (select observed from solver_test_results where label = 'worker-snapshot-count'),
  '1',
  'worker can persist a same-company immutable planning snapshot'
);
select is(
  (select observed from solver_test_results where label = 'manager-visible-count'),
  '2',
  'manager can read current-company solver attempts'
);
select is(
  (select observed from solver_test_results where label = 'worker-plan-count'),
  '1',
  'worker can persist only an independently validated proposal shape'
);
select is(
  (select observed from solver_test_results where label = 'cross-tenant-count'),
  '0',
  'planning snapshots remain invisible across companies'
);
select is(
  (select observed from solver_test_results where label = 'api-insert-denied'),
  'true',
  'API role cannot forge solver results'
);
select is(
  (select observed from solver_test_results where label = 'worker-update-denied'),
  'true',
  'worker cannot mutate frozen planning snapshots'
);

select * from finish();
rollback;
