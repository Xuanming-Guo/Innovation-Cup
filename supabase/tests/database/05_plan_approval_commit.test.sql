begin;
select plan(20);

select has_table('app', 'plan_approval_requirements', 'approval requirements exist');
select has_table('app', 'plan_approval_decisions', 'immutable approval decisions exist');
select has_table('app', 'plan_commitments', 'atomic plan commitments exist');
select has_table('app', 'committed_schedule_blocks', 'committed time ranges exist');
select has_table('app', 'outbox_intents', 'transactional outbox intents exist');
select has_table('app', 'audit_events', 'structured audit events exist');

insert into auth.users (id, instance_id, aud, role, email, encrypted_password, created_at, updated_at)
values (
  '66666666-aaaa-4aaa-8aaa-aaaaaaaaaaa6',
  '00000000-0000-0000-0000-000000000000',
  'authenticated', 'authenticated', 'approval-manager@example.invalid',
  extensions.crypt('local-test-only', extensions.gen_salt('bf')),
  clock_timestamp(), clock_timestamp()
);

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values (
  '66666666-0000-4000-8000-000000000066',
  '11111111-1111-4111-8111-111111111111',
  '66666666-aaaa-4aaa-8aaa-aaaaaaaaaaa6',
  'active', 'manager', clock_timestamp()
);

insert into app.employee_profiles (id, company_id, membership_id)
values (
  '66666666-d000-4000-8000-000000000066',
  '11111111-1111-4111-8111-111111111111',
  '66666666-0000-4000-8000-000000000066'
);

insert into app.planning_requests (
  id, company_id, requester_membership_id, original_prompt, idempotency_key, request_digest
) values (
  '66666666-1000-4000-8000-000000000066',
  '11111111-1111-4111-8111-111111111111',
  '66666666-0000-4000-8000-000000000066',
  'Commit the exact approved fixture.', 'approval-fixture-key-0001',
  decode(repeat('61', 32), 'hex')
);

insert into app.retrieval_runs (
  id, company_id, request_id, actor_membership_id, purpose, allowed_scope,
  selected_manifest, omitted_manifest, missing_manifest, projection_digest,
  projection_characters, status, started_at, completed_at
) values (
  '66666666-2000-4000-8000-000000000066',
  '11111111-1111-4111-8111-111111111111',
  '66666666-1000-4000-8000-000000000066',
  '66666666-0000-4000-8000-000000000066',
  'approval-test', '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
  decode(repeat('62', 32), 'hex'), 20, 'complete', clock_timestamp(), clock_timestamp()
);

insert into app.interpretation_runs (
  id, company_id, request_id, retrieval_run_id, model_id, sdk_version,
  prompt_version, schema_version, safety_profile, configuration, status,
  outcome, started_at, completed_at
) values (
  '66666666-3000-4000-8000-000000000066',
  '11111111-1111-4111-8111-111111111111',
  '66666666-1000-4000-8000-000000000066',
  '66666666-2000-4000-8000-000000000066',
  'fixture', '2.23.0', 'interpretation-v1', 'candidate-task-contract.v1',
  'provider-default-no-tools-v1', '{}'::jsonb, 'completed', 'admitted',
  clock_timestamp(), clock_timestamp()
);

insert into app.candidate_contracts (
  id, company_id, request_id, interpretation_run_id, contract_json,
  contract_digest, admission_status, validation_issues
) values (
  '66666666-4000-4000-8000-000000000066',
  '11111111-1111-4111-8111-111111111111',
  '66666666-1000-4000-8000-000000000066',
  '66666666-3000-4000-8000-000000000066',
  '{"schema_version":"candidate-task-contract.v1"}'::jsonb,
  decode(repeat('63', 32), 'hex'), 'admitted', '[]'::jsonb
);

insert into app.validated_constraints (
  id, company_id, request_id, candidate_contract_id, constraint_key,
  schema_version, strength, payload, source_version_ids, authority_refs,
  confidentiality, negotiability, confirmation, constraint_digest
) values (
  '66666666-5000-4000-8000-000000000066',
  '11111111-1111-4111-8111-111111111111',
  '66666666-1000-4000-8000-000000000066',
  '66666666-4000-4000-8000-000000000066',
  'task.commit', 'validated-constraint.v1', 'hard',
  '{"family":"task_definition","task_id":"66666666-c000-4000-8000-000000000066","task_key":"commit","title":"Commit approved work","scheduling_kind":"flexible_active"}'::jsonb,
  '[]'::jsonb, '["manager:fixture"]'::jsonb, 'company', 'locked', 'confirmed',
  decode(repeat('64', 32), 'hex')
);

insert into app.planning_snapshots (
  id, company_id, request_id, candidate_contract_id, schema_version,
  base_company_revision, horizon_start, horizon_end, slot_minutes,
  source_manifest_digest, permission_revision, profile_revision,
  estimate_revision, compiler_version, policy, normalized_snapshot,
  snapshot_digest, frozen_at
) values (
  '66666666-6000-4000-8000-000000000066',
  '11111111-1111-4111-8111-111111111111',
  '66666666-1000-4000-8000-000000000066',
  '66666666-4000-4000-8000-000000000066',
  'planning-snapshot.v1', 0, '2026-09-28 09:00:00+00', '2026-09-28 11:00:00+00', 30,
  decode(repeat('65', 32), 'hex'), 'permissions:1', 'profiles:1', 'estimates:1',
  'coordination-z3-compiler.v1', '{"policy_version":"planning-v1"}'::jsonb, '{}'::jsonb,
  decode(repeat('66', 32), 'hex'), clock_timestamp()
);

insert into app.planning_snapshot_constraints (company_id, snapshot_id, constraint_id, ordinal)
values (
  '11111111-1111-4111-8111-111111111111',
  '66666666-6000-4000-8000-000000000066',
  '66666666-5000-4000-8000-000000000066', 0
);

insert into app.solver_runs (
  id, company_id, snapshot_id, scope, application_classification, raw_status,
  termination, model_digest, compiler_version, solver_version, validator_version,
  timeout_ms, resource_limit, runtime_ms, objective_vector,
  diagnostic_constraint_keys, validation_report, started_at, completed_at
) values
  (
    '66666666-7000-4000-8000-000000000066',
    '11111111-1111-4111-8111-111111111111',
    '66666666-6000-4000-8000-000000000066', 'pinned_insertion', 'FEASIBLE',
    'sat', 'completed', decode(repeat('67', 32), 'hex'), 'coordination-z3-compiler.v1',
    '5.1.0.0', 'coordination-schedule-validator.v1', 5000, 10000000, 8,
    '[]'::jsonb, '[]'::jsonb, '{"valid":true}'::jsonb,
    clock_timestamp(), clock_timestamp()
  ),
  (
    '66666666-7000-4000-8000-000000000067',
    '11111111-1111-4111-8111-111111111111',
    '66666666-6000-4000-8000-000000000066', 'pinned_insertion', 'FEASIBLE',
    'sat', 'completed', decode(repeat('68', 32), 'hex'), 'coordination-z3-compiler.v1',
    '5.1.0.0', 'coordination-schedule-validator.v1', 5000, 10000000, 8,
    '[]'::jsonb, '[]'::jsonb, '{"valid":true}'::jsonb,
    clock_timestamp(), clock_timestamp()
  );

insert into app.plans (
  id, company_id, request_id, snapshot_id, solver_run_id, state, classification, proposal_digest
) values
  (
    '66666666-8000-4000-8000-000000000066',
    '11111111-1111-4111-8111-111111111111',
    '66666666-1000-4000-8000-000000000066',
    '66666666-6000-4000-8000-000000000066',
    '66666666-7000-4000-8000-000000000066',
    'proposed', 'FEASIBLE', decode(repeat('69', 32), 'hex')
  ),
  (
    '66666666-8000-4000-8000-000000000067',
    '11111111-1111-4111-8111-111111111111',
    '66666666-1000-4000-8000-000000000066',
    '66666666-6000-4000-8000-000000000066',
    '66666666-7000-4000-8000-000000000067',
    'proposed', 'FEASIBLE', decode(repeat('6a', 32), 'hex')
  );

insert into app.plan_task_placements (
  company_id, plan_id, task_id, start_slot, end_slot, owner_resource_id
) values
  ('11111111-1111-4111-8111-111111111111', '66666666-8000-4000-8000-000000000066',
   '66666666-c000-4000-8000-000000000066', 0, 2, '66666666-d000-4000-8000-000000000066'),
  ('11111111-1111-4111-8111-111111111111', '66666666-8000-4000-8000-000000000067',
   '66666666-c000-4000-8000-000000000066', 0, 2, '66666666-d000-4000-8000-000000000066');

insert into app.plan_schedule_blocks (
  company_id, plan_id, task_id, resource_id, start_slot, end_slot, capacity_units, block_role
) values
  ('11111111-1111-4111-8111-111111111111', '66666666-8000-4000-8000-000000000066',
   '66666666-c000-4000-8000-000000000066', '66666666-d000-4000-8000-000000000066',
   0, 2, 1, 'owner'),
  ('11111111-1111-4111-8111-111111111111', '66666666-8000-4000-8000-000000000067',
   '66666666-c000-4000-8000-000000000066', '66666666-d000-4000-8000-000000000066',
   0, 2, 1, 'owner');

insert into app.plan_approval_requirements (
  id, company_id, plan_id, approval_domain, requirement_kind, authority_kind,
  artifact_digest, proposal_digest, snapshot_digest, source_manifest_digest,
  base_company_revision, policy_revision, policy_version, reason
) values
  ('66666666-9000-4000-8000-000000000066', '11111111-1111-4111-8111-111111111111',
   '66666666-8000-4000-8000-000000000066', 'planning', 'plan_commit', 'company_manager',
   decode(repeat('69', 32), 'hex'), decode(repeat('69', 32), 'hex'),
   decode(repeat('66', 32), 'hex'), decode(repeat('65', 32), 'hex'), 0, 0,
   'planning-v1', 'Approve exact fixture one.'),
  ('66666666-9000-4000-8000-000000000067', '11111111-1111-4111-8111-111111111111',
   '66666666-8000-4000-8000-000000000067', 'planning', 'plan_commit', 'company_manager',
   decode(repeat('6a', 32), 'hex'), decode(repeat('6a', 32), 'hex'),
   decode(repeat('66', 32), 'hex'), decode(repeat('65', 32), 'hex'), 0, 0,
   'planning-v1', 'Approve exact fixture two.');

insert into app.employee_brief_versions (
  id, company_id, plan_id, version, brief_payload, audience_scope, brief_digest
) values (
  '66666666-9500-4000-8000-000000000066',
  '11111111-1111-4111-8111-111111111111',
  '66666666-8000-4000-8000-000000000066', 1,
  '{"summary":"Complete the committed fixture."}'::jsonb,
  '{"employee_ids":["66666666-d000-4000-8000-000000000066"]}'::jsonb,
  decode(repeat('6b', 32), 'hex')
);

create temporary table approval_results (label text primary key, observed text not null) on commit drop;
grant insert, select on table approval_results to coordination_api;

set local role coordination_api;
select set_config('app.actor_id', '66666666-aaaa-4aaa-8aaa-aaaaaaaaaaa6', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:approval-commit', true);

select app.record_plan_approval_decision(
  '11111111-1111-4111-8111-111111111111', '66666666-8000-4000-8000-000000000066',
  '66666666-9000-4000-8000-000000000066', 'approved', '',
  decode(repeat('69', 32), 'hex'), decode(repeat('69', 32), 'hex'),
  decode(repeat('66', 32), 'hex'), decode(repeat('65', 32), 'hex'),
  0, 0, 'planning-v1', 'approval-operation-0001', decode(repeat('71', 32), 'hex'),
  '66666666-a000-4000-8000-000000000066'
);
select app.record_plan_approval_decision(
  '11111111-1111-4111-8111-111111111111', '66666666-8000-4000-8000-000000000067',
  '66666666-9000-4000-8000-000000000067', 'approved', '',
  decode(repeat('6a', 32), 'hex'), decode(repeat('6a', 32), 'hex'),
  decode(repeat('66', 32), 'hex'), decode(repeat('65', 32), 'hex'),
  0, 0, 'planning-v1', 'approval-operation-0002', decode(repeat('72', 32), 'hex'),
  '66666666-a000-4000-8000-000000000067'
);
select app.record_plan_approval_decision(
  '11111111-1111-4111-8111-111111111111', '66666666-8000-4000-8000-000000000066',
  (select id from app.plan_approval_requirements
   where company_id = '11111111-1111-4111-8111-111111111111'
     and plan_id = '66666666-8000-4000-8000-000000000066'
     and approval_domain = 'disclosure'),
  'approved', '', decode(repeat('6b', 32), 'hex'), decode(repeat('69', 32), 'hex'),
  decode(repeat('66', 32), 'hex'), decode(repeat('65', 32), 'hex'), 0, 0,
  'planning-v1', 'approval-disclosure-operation-0001', decode(repeat('75', 32), 'hex'),
  '66666666-a000-4000-8000-000000000068'
);

insert into approval_results
select 'commit', commit_status
from app.commit_approved_plan(
    '11111111-1111-4111-8111-111111111111', '66666666-8000-4000-8000-000000000066',
    decode(repeat('69', 32), 'hex'), decode(repeat('66', 32), 'hex'),
    decode(repeat('65', 32), 'hex'), 0, 0, 'planning-v1',
    'commit-operation-0001', decode(repeat('73', 32), 'hex'),
    '66666666-b000-4000-8000-000000000066'
  );

insert into approval_results
select 'replay', replayed::text
from app.commit_approved_plan(
    '11111111-1111-4111-8111-111111111111', '66666666-8000-4000-8000-000000000066',
    decode(repeat('69', 32), 'hex'), decode(repeat('66', 32), 'hex'),
    decode(repeat('65', 32), 'hex'), 0, 0, 'planning-v1',
    'commit-operation-0001', decode(repeat('73', 32), 'hex'),
    '66666666-b000-4000-8000-000000000066'
  );

do $$
begin
  begin
    perform app.commit_approved_plan(
      '11111111-1111-4111-8111-111111111111', '66666666-8000-4000-8000-000000000067',
      decode(repeat('6a', 32), 'hex'), decode(repeat('66', 32), 'hex'),
      decode(repeat('65', 32), 'hex'), 0, 0, 'planning-v1',
      'commit-operation-0002', decode(repeat('74', 32), 'hex'),
      '66666666-b000-4000-8000-000000000067'
    );
    insert into approval_results values ('stale-second', 'false');
  exception when serialization_failure then
    insert into approval_results values ('stale-second', 'true');
  end;
end
$$;

reset role;
insert into approval_results values
  ('approval-count', (select count(*)::text from app.plan_approval_decisions)),
  ('work-count', (select count(*)::text from app.work_items)),
  ('block-count', (select count(*)::text from app.committed_schedule_blocks)),
  ('use-count', (select count(*)::text from app.plan_approval_uses)),
  ('outbox-count', (select count(*)::text from app.outbox_intents)),
  ('audit-count', (select count(*)::text from app.audit_events)),
  ('disclosure-count', (select count(*)::text from app.plan_approval_requirements
                        where approval_domain = 'disclosure')),
  ('brief-publish-count', (select count(*)::text from app.outbox_intents
                           where intent_kind = 'employee_brief.publish')),
  ('assignment-notification-count', (select count(*)::text from app.outbox_intents
                                     where intent_kind = 'task.changed'
                                       and payload ->> 'event' = 'assigned')),
  ('brief-readable', app.can_read_employee_brief(
                       '66666666-aaaa-4aaa-8aaa-aaaaaaaaaaa6',
                       '11111111-1111-4111-8111-111111111111',
                       '66666666-9500-4000-8000-000000000066')::text),
  ('revision', (select planning_revision::text from app.companies
                where id = '11111111-1111-4111-8111-111111111111'));

select is((select observed from approval_results where label = 'approval-count'), '3',
  'planning and disclosure approvals are recorded before shared state changes');
select is((select observed from approval_results where label = 'commit'), 'committed',
  'the approved plan commits atomically');
select is((select observed from approval_results where label = 'replay'), 'true',
  'an identical commit request is idempotent');
select is((select observed from approval_results where label = 'stale-second'), 'true',
  'a competing plan at the old base revision receives an explicit stale result');
select is((select observed from approval_results where label = 'work-count'), '1',
  'committed work matches the one validated placement');
select is((select observed from approval_results where label = 'block-count'), '1',
  'committed blocks match the independently validated candidate');
select is((select observed from approval_results where label = 'revision'), '1',
  'the authoritative planning revision advances exactly once');
select is((select observed from approval_results where label = 'use-count'), '1',
  'the consumed exact approval is linked to the commitment');
select is((select observed from approval_results where label = 'outbox-count'), '3',
  'plan, assignment and approved-brief intents are committed in the same transaction');
select is((select observed from approval_results where label = 'audit-count'), '4',
  'approval and commitment audit events retain actor, policy and digest context');
select is((select observed from approval_results where label = 'disclosure-count'), '1',
  'a brief automatically receives a separate exact disclosure requirement');
select is((select observed from approval_results where label = 'brief-publish-count'), '1',
  'an approved brief is published only once the plan is committed');
select is((select observed from approval_results where label = 'assignment-notification-count'), '1',
  'committing an owner assignment emits one employee task invalidation intent');
select is((select observed from approval_results where label = 'brief-readable'), 'true',
  'the corrected employee-brief argument order authorises the intended audience');

select * from finish();
rollback;
