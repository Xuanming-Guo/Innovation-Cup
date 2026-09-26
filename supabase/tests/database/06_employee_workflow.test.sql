begin;
select plan(48);

select has_table('app', 'execution_resources', 'execution resources exist');
select has_table('app', 'task_review_policies', 'versioned task review policies exist');
select has_table('app', 'task_access_grants', 'task-scoped access grants exist');
select has_table('app', 'task_events', 'task lifecycle events exist');
select has_table('app', 'submissions', 'versioned submissions exist');
select has_table('app', 'task_reviews', 'exact submission reviews exist');
select has_table('app', 'employee_workload_state', 'operational workload state exists');

insert into auth.users (
  id, instance_id, aud, role, email, encrypted_password, created_at, updated_at
) values
  ('77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa1', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'workflow-manager@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')), clock_timestamp(), clock_timestamp()),
  ('77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa2', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'workflow-owner@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')), clock_timestamp(), clock_timestamp()),
  ('77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa3', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'workflow-reviewer-one@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')), clock_timestamp(), clock_timestamp()),
  ('77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa4', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'workflow-reviewer-two@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')), clock_timestamp(), clock_timestamp()),
  ('77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa5', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'workflow-bystander-manager@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')), clock_timestamp(), clock_timestamp());

update app.user_profiles set display_name = case user_id
  when '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa1' then 'Morgan Manager'
  when '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa2' then 'Alex Owner'
  when '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa3' then 'Riley Reviewer'
  when '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa4' then 'Casey Reviewer'
  else 'Taylor Bystander' end
where user_id::text like '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa_';

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values
  ('77777777-0000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
   '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa1', 'active', 'manager', clock_timestamp()),
  ('77777777-0000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
   '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa2', 'active', 'member', clock_timestamp()),
  ('77777777-0000-4000-8000-000000000003', '11111111-1111-4111-8111-111111111111',
   '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa3', 'active', 'member', clock_timestamp()),
  ('77777777-0000-4000-8000-000000000004', '11111111-1111-4111-8111-111111111111',
   '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa4', 'active', 'member', clock_timestamp()),
  ('77777777-0000-4000-8000-000000000005', '11111111-1111-4111-8111-111111111111',
   '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa5', 'active', 'manager', clock_timestamp());

insert into app.employee_profiles (id, company_id, membership_id) values
  ('77777777-e000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
   '77777777-0000-4000-8000-000000000001'),
  ('77777777-e000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
   '77777777-0000-4000-8000-000000000002'),
  ('77777777-e000-4000-8000-000000000003', '11111111-1111-4111-8111-111111111111',
   '77777777-0000-4000-8000-000000000003'),
  ('77777777-e000-4000-8000-000000000004', '11111111-1111-4111-8111-111111111111',
   '77777777-0000-4000-8000-000000000004'),
  ('77777777-e000-4000-8000-000000000005', '11111111-1111-4111-8111-111111111111',
   '77777777-0000-4000-8000-000000000005');

insert into app.planning_requests (
  id, company_id, requester_membership_id, original_prompt, idempotency_key, request_digest
) values (
  '77777777-1000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '77777777-0000-4000-8000-000000000001', 'Complete a reviewed employee task.',
  'employee-fixture-request-0001', decode(repeat('11', 32), 'hex')
);
insert into app.retrieval_runs (
  id, company_id, request_id, actor_membership_id, purpose, allowed_scope,
  selected_manifest, omitted_manifest, missing_manifest, projection_digest,
  projection_characters, status, started_at, completed_at
) values (
  '77777777-2000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '77777777-1000-4000-8000-000000000001', '77777777-0000-4000-8000-000000000001',
  'employee-workflow-test', '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
  decode(repeat('12', 32), 'hex'), 30, 'complete', clock_timestamp(), clock_timestamp()
);
insert into app.interpretation_runs (
  id, company_id, request_id, retrieval_run_id, model_id, sdk_version,
  prompt_version, schema_version, safety_profile, configuration, status,
  outcome, started_at, completed_at
) values (
  '77777777-3000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '77777777-1000-4000-8000-000000000001', '77777777-2000-4000-8000-000000000001',
  'fixture', '2.23.0', 'interpretation-v1', 'candidate-task-contract.v1',
  'provider-default-no-tools-v1', '{}'::jsonb, 'completed', 'admitted',
  clock_timestamp(), clock_timestamp()
);
insert into app.candidate_contracts (
  id, company_id, request_id, interpretation_run_id, contract_json,
  contract_digest, admission_status, validation_issues
) values (
  '77777777-4000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '77777777-1000-4000-8000-000000000001', '77777777-3000-4000-8000-000000000001',
  '{"schema_version":"candidate-task-contract.v1"}'::jsonb,
  decode(repeat('13', 32), 'hex'), 'admitted', '[]'::jsonb
);
insert into app.planning_snapshots (
  id, company_id, request_id, candidate_contract_id, schema_version,
  base_company_revision, horizon_start, horizon_end, slot_minutes,
  source_manifest_digest, permission_revision, profile_revision,
  estimate_revision, compiler_version, policy, normalized_snapshot,
  snapshot_digest, frozen_at
) values (
  '77777777-5000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '77777777-1000-4000-8000-000000000001', '77777777-4000-4000-8000-000000000001',
  'planning-snapshot.v1', 0, clock_timestamp(), clock_timestamp() + interval '1 day', 30,
  decode(repeat('14', 32), 'hex'), 'permissions:1', 'profiles:1', 'estimates:1',
  'coordination-z3-compiler.v1', '{"policy_version":"planning-v1"}'::jsonb,
  '{}'::jsonb, decode(repeat('15', 32), 'hex'), clock_timestamp()
);
insert into app.solver_runs (
  id, company_id, snapshot_id, scope, application_classification, raw_status,
  termination, model_digest, compiler_version, solver_version, validator_version,
  timeout_ms, resource_limit, runtime_ms, objective_vector,
  diagnostic_constraint_keys, validation_report, started_at, completed_at
) values (
  '77777777-6000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '77777777-5000-4000-8000-000000000001', 'pinned_insertion', 'FEASIBLE', 'sat',
  'completed', decode(repeat('16', 32), 'hex'), 'coordination-z3-compiler.v1',
  '5.1.0.0', 'coordination-schedule-validator.v1', 5000, 10000000, 9,
  '[]'::jsonb, '[]'::jsonb, '{"valid":true}'::jsonb, clock_timestamp(), clock_timestamp()
);
insert into app.plans (
  id, company_id, request_id, snapshot_id, solver_run_id, state, classification, proposal_digest
) values (
  '77777777-7000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '77777777-1000-4000-8000-000000000001', '77777777-5000-4000-8000-000000000001',
  '77777777-6000-4000-8000-000000000001', 'proposed', 'FEASIBLE',
  decode(repeat('17', 32), 'hex')
);
insert into app.plan_commitments (
  id, company_id, plan_id, committed_by_membership_id, proposal_digest,
  snapshot_digest, source_manifest_digest, base_company_revision,
  committed_company_revision, policy_revision, policy_version,
  idempotency_key, command_digest, correlation_id
) values (
  '77777777-7100-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '77777777-7000-4000-8000-000000000001', '77777777-0000-4000-8000-000000000001',
  decode(repeat('17', 32), 'hex'), decode(repeat('15', 32), 'hex'),
  decode(repeat('14', 32), 'hex'), 0, 1, 0, 'planning-v1',
  'employee-plan-commit-0001', decode(repeat('18', 32), 'hex'),
  '77777777-7200-4000-8000-000000000001'
);
insert into app.employee_brief_versions (
  id, company_id, plan_id, version, brief_payload, audience_scope, brief_digest
) values (
  '77777777-8000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '77777777-7000-4000-8000-000000000001', 1,
  '{"purpose":"Publish the approved runbook","deliverable":"One reviewed runbook","permissions":["internal-docs"]}'::jsonb,
  '{"employee_ids":["77777777-e000-4000-8000-000000000002"]}'::jsonb,
  decode(repeat('19', 32), 'hex')
);
insert into app.plan_approval_decisions (
  company_id, plan_id, requirement_id, actor_membership_id, decision,
  artifact_digest, proposal_digest, snapshot_digest, source_manifest_digest,
  base_company_revision, policy_revision, policy_version, idempotency_key,
  command_digest, expires_at
)
select requirement.company_id, requirement.plan_id, requirement.id,
       '77777777-0000-4000-8000-000000000001', 'approved',
       requirement.artifact_digest, requirement.proposal_digest,
       requirement.snapshot_digest, requirement.source_manifest_digest,
       requirement.base_company_revision, requirement.policy_revision,
       requirement.policy_version, 'employee-disclosure-0001',
       decode(repeat('1a', 32), 'hex'), clock_timestamp() + interval '1 day'
from app.plan_approval_requirements as requirement
where requirement.company_id = '11111111-1111-4111-8111-111111111111'
  and requirement.plan_id = '77777777-7000-4000-8000-000000000001'
  and requirement.approval_domain = 'disclosure';

insert into app.work_items (
  company_id, task_id, source_request_id, source_plan_id, task_key, title,
  scheduling_kind, start_at, finish_at, owner_resource_id, committed_company_revision
) values (
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  '77777777-1000-4000-8000-000000000001', '77777777-7000-4000-8000-000000000001',
  'publish-runbook', 'Publish the approved runbook', 'flexible_active',
  date_trunc('day', clock_timestamp()) + interval '9 hours',
  date_trunc('day', clock_timestamp()) + interval '11 hours',
  '77777777-e000-4000-8000-000000000002', 1
);
insert into app.work_assignments (
  company_id, task_id, resource_id, assignment_role, capacity_units, source_plan_id
) values (
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  '77777777-e000-4000-8000-000000000002', 'owner', 1,
  '77777777-7000-4000-8000-000000000001'
);

insert into app.private_files (
  id, company_id, bucket_id, object_path, purpose, uploader_employee_id,
  display_filename, declared_mime_type, detected_mime_type, size_bytes,
  state, upload_intent_expires_at, uploaded_at
) values
  ('77777777-f000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
   'coordination-quarantine',
   '11111111-1111-4111-8111-111111111111/77777777-f000-4000-8000-000000000001/quarantine/runbook.pdf',
   'submission', '77777777-e000-4000-8000-000000000002', 'runbook.pdf',
   'application/pdf', 'application/pdf', 12, 'pending_upload',
   clock_timestamp() + interval '10 minutes', clock_timestamp()),
  ('77777777-f000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
   'coordination-quarantine',
   '11111111-1111-4111-8111-111111111111/77777777-f000-4000-8000-000000000002/quarantine/wrong.pdf',
   'submission', '77777777-e000-4000-8000-000000000002', 'wrong.pdf',
   'application/pdf', 'application/pdf', 12, 'pending_upload',
   clock_timestamp() + interval '10 minutes', clock_timestamp());

update app.private_files set state = 'quarantined'
where id in (
  '77777777-f000-4000-8000-000000000001',
  '77777777-f000-4000-8000-000000000002'
);

create temporary table employee_results (
  label text primary key,
  observed text not null
) on commit drop;
grant insert, select, update on table employee_results to coordination_api, coordination_worker;
create temporary table employee_scan_leases (
  job_id uuid, company_id uuid, job_kind text, aggregate_id uuid, payload jsonb,
  requested_by_membership_id uuid, requested_by_user_id uuid,
  administrative_role text, employee_id uuid, correlation_id uuid,
  attempt_count integer, max_attempts integer, lease_token uuid,
  leased_until timestamptz
) on commit drop;
grant insert, select on table employee_scan_leases to coordination_worker;

insert into employee_results values
  ('initial-status', (select status from app.work_items where task_id = '77777777-9000-4000-8000-000000000001')),
  ('brief-bound', (select count(*)::text from app.work_items where task_id = '77777777-9000-4000-8000-000000000001' and employee_brief_version_id = '77777777-8000-4000-8000-000000000001')),
  ('initial-workload', (select assigned_count::text from app.employee_workload_state where employee_id = '77777777-e000-4000-8000-000000000002'));

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:set-review-policy', true);
do $$
begin
  begin
    perform app.set_task_review_policy(
      '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
      '77777777-e000-4000-8000-000000000002', false, '', 1,
      'employee-self-review-0001', decode(repeat('21', 32), 'hex'),
      '77777777-a000-4000-8000-000000000001'
    );
    insert into employee_results values ('self-review-rejected', 'false');
  exception when invalid_parameter_value then
    insert into employee_results values ('self-review-rejected', 'true');
  end;
end
$$;
insert into employee_results
select 'policy-one-version', policy_version::text from app.set_task_review_policy(
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  '77777777-e000-4000-8000-000000000003', false, '', 1,
  'employee-review-policy-0001', decode(repeat('22', 32), 'hex'),
  '77777777-a000-4000-8000-000000000002'
);
insert into employee_results
select 'policy-one-task-version', task_version::text from app.set_task_review_policy(
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  '77777777-e000-4000-8000-000000000003', false, '', 1,
  'employee-review-policy-0001', decode(repeat('22', 32), 'hex'),
  '77777777-a000-4000-8000-000000000002'
);
reset role;

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa2', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:employee-task', true);
insert into employee_results values
  ('owner-task-count', (select count(*)::text from app.work_items where task_id = '77777777-9000-4000-8000-000000000001')),
  ('owner-brief-count', (select count(*)::text from app.employee_brief_versions where id = '77777777-8000-4000-8000-000000000001'));
insert into employee_results
select 'ack-status', task_status from app.transition_employee_task(
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  'acknowledge', 2, '{}'::jsonb, 'employee-ack-command-0001',
  decode(repeat('23', 32), 'hex'), '77777777-a000-4000-8000-000000000003'
);
insert into employee_results
select 'ack-replayed', replayed::text from app.transition_employee_task(
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  'acknowledge', 2, '{}'::jsonb, 'employee-ack-command-0001',
  decode(repeat('23', 32), 'hex'), '77777777-a000-4000-8000-000000000003'
);
do $$
begin
  begin
    perform app.transition_employee_task(
      '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
      'start', 3, '{}'::jsonb, 'employee-ack-command-0001',
      decode(repeat('24', 32), 'hex'), '77777777-a000-4000-8000-000000000004'
    );
    insert into employee_results values ('idempotency-conflict', 'false');
  exception when unique_violation then
    insert into employee_results values ('idempotency-conflict', 'true');
  end;
end
$$;
insert into employee_results
select 'start-status', task_status from app.transition_employee_task(
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  'start', 3, '{}'::jsonb, 'employee-start-command-0001',
  decode(repeat('25', 32), 'hex'), '77777777-a000-4000-8000-000000000005'
);
select * from app.transition_employee_task(
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  'flag_skill', 4, '{"detail":"Needs approved accessibility support"}'::jsonb,
  'employee-skill-flag-0001', decode(repeat('26', 32), 'hex'),
  '77777777-a000-4000-8000-000000000006'
);
insert into employee_results values
  ('owner-correction-count', (select count(*)::text from app.task_corrections)),
  ('flag-event-safe', (select (event_payload ? 'detail')::text from app.task_events where event_type = 'skill_flagged'));
do $$
begin
  begin
    perform app.submit_employee_task(
      '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
      'Pending evidence must fail.', '[]'::jsonb,
      '["77777777-f000-4000-8000-000000000001"]'::jsonb, 30, 4,
      decode(repeat('31', 32), 'hex'), 'employee-pending-submit-0001',
      decode(repeat('32', 32), 'hex'), '77777777-a000-4000-8000-000000000007'
    );
    insert into employee_results values ('pending-file-rejected', 'false');
  exception when invalid_parameter_value then
    insert into employee_results values ('pending-file-rejected', 'true');
  end;
end
$$;
reset role;

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa3', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:correction-privacy', true);
insert into employee_results values
  ('reviewer-correction-count', (select count(*)::text from app.task_corrections));
reset role;

set local role coordination_worker;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:file-scan', true);
insert into employee_scan_leases
select * from app.lease_durable_jobs(
  '77777777-b000-4000-8000-000000000001', 32, 60
);
do $$
begin
  begin
    perform app.record_leased_private_file_scan(
      '11111111-1111-4111-8111-111111111111',
      (select job_id from employee_scan_leases
       where aggregate_id = '77777777-f000-4000-8000-000000000002'),
      '77777777-b000-4000-8000-000000000001',
      (select lease_token from employee_scan_leases
       where aggregate_id = '77777777-f000-4000-8000-000000000002'),
      '77777777-f000-4000-8000-000000000002',
      'clean', 'text/plain', 12, decode(repeat('33', 32), 'hex'), 'fixture-scanner-v1',
      '11111111-1111-4111-8111-111111111111/77777777-f000-4000-8000-000000000002/final/wrong.pdf'
    );
    insert into employee_results values ('invalid-scan-rejected', 'false');
  exception when invalid_parameter_value then
    insert into employee_results values ('invalid-scan-rejected', 'true');
  end;
end
$$;
insert into employee_results
select 'clean-scan-state', app.record_leased_private_file_scan(
  '11111111-1111-4111-8111-111111111111',
  (select job_id from employee_scan_leases
   where aggregate_id = '77777777-f000-4000-8000-000000000001'),
  '77777777-b000-4000-8000-000000000001',
  (select lease_token from employee_scan_leases
   where aggregate_id = '77777777-f000-4000-8000-000000000001'),
  '77777777-f000-4000-8000-000000000001',
  'clean', 'application/pdf', 12, decode(repeat('34', 32), 'hex'), 'fixture-scanner-v1',
  '11111111-1111-4111-8111-111111111111/77777777-f000-4000-8000-000000000001/final/runbook.pdf'
);
reset role;

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa2', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:first-submission', true);
insert into employee_results
select 'submission-one-version', submission_version::text from app.submit_employee_task(
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  'The reviewed runbook is attached.', '["ticket:OPS-42"]'::jsonb,
  '["77777777-f000-4000-8000-000000000001"]'::jsonb, 30, 4,
  decode(repeat('35', 32), 'hex'), 'employee-submit-command-0001',
  decode(repeat('36', 32), 'hex'), '77777777-a000-4000-8000-000000000008'
);
insert into employee_results
select 'submission-one-replay', replayed::text from app.submit_employee_task(
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  'The reviewed runbook is attached.', '["ticket:OPS-42"]'::jsonb,
  '["77777777-f000-4000-8000-000000000001"]'::jsonb, 30, 4,
  decode(repeat('35', 32), 'hex'), 'employee-submit-command-0001',
  decode(repeat('36', 32), 'hex'), '77777777-a000-4000-8000-000000000008'
);
reset role;

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:replace-review-policy', true);
insert into employee_results
select 'policy-two-version', policy_version::text from app.set_task_review_policy(
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  '77777777-e000-4000-8000-000000000004', false, '', 5,
  'employee-review-policy-0002', decode(repeat('37', 32), 'hex'),
  '77777777-a000-4000-8000-000000000009'
);
reset role;

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa4', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:wrong-reviewer', true);
do $$
begin
  begin
    perform app.review_task_submission(
      '11111111-1111-4111-8111-111111111111',
      (select id from app.submissions where task_id = '77777777-9000-4000-8000-000000000001' and version = 1),
      1, decode(repeat('35', 32), 'hex'), 'accepted', '[]'::jsonb, '',
      'employee-wrong-review-0001', decode(repeat('38', 32), 'hex'),
      '77777777-a000-4000-8000-000000000010'
    );
    insert into employee_results values ('new-reviewer-v1-rejected', 'false');
  exception when insufficient_privilege then
    insert into employee_results values ('new-reviewer-v1-rejected', 'true');
  end;
end
$$;
reset role;

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa3', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:bound-reviewer', true);
insert into employee_results values
  ('bound-reviewer-submission-count', (select count(*)::text from app.submissions where version = 1));
do $$
begin
  begin
    perform app.review_task_submission(
      '11111111-1111-4111-8111-111111111111',
      (select id from app.submissions where task_id = '77777777-9000-4000-8000-000000000001' and version = 1),
      1, decode(repeat('ff', 32), 'hex'), 'accepted', '[]'::jsonb, '',
      'employee-wrong-digest-0001', decode(repeat('39', 32), 'hex'),
      '77777777-a000-4000-8000-000000000011'
    );
    insert into employee_results values ('wrong-digest-rejected', 'false');
  exception when serialization_failure then
    insert into employee_results values ('wrong-digest-rejected', 'true');
  end;
end
$$;
insert into employee_results
select 'revision-status', task_status from app.review_task_submission(
  '11111111-1111-4111-8111-111111111111',
  (select id from app.submissions where task_id = '77777777-9000-4000-8000-000000000001' and version = 1),
  1, decode(repeat('35', 32), 'hex'), 'revision_requested',
  '[{"criterion":"accessibility","passed":false}]'::jsonb,
  'Add an accessible text alternative.', 'employee-revision-review-0001',
  decode(repeat('3a', 32), 'hex'), '77777777-a000-4000-8000-000000000012'
);
reset role;

insert into employee_results values
  ('profile-after-revision', (select profile_revision::text from app.employee_profiles where id = '77777777-e000-4000-8000-000000000002')),
  ('first-evidence-state', (select correction_state from app.familiarity_evidence where contribution_stage = 'submitted' and submission_id = (select id from app.submissions where version = 1 and task_id = '77777777-9000-4000-8000-000000000001')));

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa2', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:second-submission', true);
insert into employee_results
select 'submission-two-version', submission_version::text from app.submit_employee_task(
  '11111111-1111-4111-8111-111111111111', '77777777-9000-4000-8000-000000000001',
  'The accessible revision is ready.', '[]'::jsonb, '[]'::jsonb, 45, 7,
  decode(repeat('3b', 32), 'hex'), 'employee-submit-command-0002',
  decode(repeat('3c', 32), 'hex'), '77777777-a000-4000-8000-000000000013'
);
reset role;

insert into employee_results
select 'submission-two-id', id::text from app.submissions
where task_id = '77777777-9000-4000-8000-000000000001' and version = 2;

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa3', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:old-reviewer', true);
do $$
begin
  begin
    perform app.review_task_submission(
      '11111111-1111-4111-8111-111111111111',
      (select observed::uuid from employee_results where label = 'submission-two-id'),
      2, decode(repeat('3b', 32), 'hex'), 'accepted', '[]'::jsonb, '',
      'employee-old-reviewer-0001', decode(repeat('3d', 32), 'hex'),
      '77777777-a000-4000-8000-000000000014'
    );
    insert into employee_results values ('old-reviewer-v2-rejected', 'false');
  exception when insufficient_privilege then
    insert into employee_results values ('old-reviewer-v2-rejected', 'true');
  end;
end
$$;
reset role;

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa4', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:accept-revision', true);
insert into employee_results
select 'accepted-status', task_status from app.review_task_submission(
  '11111111-1111-4111-8111-111111111111',
  (select id from app.submissions where task_id = '77777777-9000-4000-8000-000000000001' and version = 2),
  2, decode(repeat('3b', 32), 'hex'), 'accepted',
  '[{"criterion":"accessibility","passed":true}]'::jsonb, '',
  'employee-accept-review-0001', decode(repeat('3e', 32), 'hex'),
  '77777777-a000-4000-8000-000000000015'
);
reset role;

set local role coordination_api;
select set_config('app.actor_id', '77777777-aaaa-4aaa-8aaa-aaaaaaaaaaa5', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:bystander-manager', true);
insert into employee_results values
  ('bystander-task-count', (select count(*)::text from app.work_items where task_id = '77777777-9000-4000-8000-000000000001')),
  ('bystander-brief-count', (select count(*)::text from app.employee_brief_versions where id = '77777777-8000-4000-8000-000000000001')),
  ('bystander-file-count', (select count(*)::text from app.private_files where id = '77777777-f000-4000-8000-000000000001')),
  ('bystander-correction-count', (select count(*)::text from app.task_corrections));
reset role;

insert into employee_results values
  ('profile-after-acceptance', (select profile_revision::text from app.employee_profiles where id = '77777777-e000-4000-8000-000000000002')),
  ('accepted-owner-evidence', (select count(*)::text from app.familiarity_evidence where employee_id = '77777777-e000-4000-8000-000000000002' and contribution_stage = 'accepted')),
  ('accepted-other-evidence', (select count(*)::text from app.familiarity_evidence where employee_id <> '77777777-e000-4000-8000-000000000002' and contribution_stage = 'accepted')),
  ('accepted-effort-minutes', (select reported_active_minutes::text from app.effort_observations where evidence_maturity = 'accepted')),
  ('review-policy-version', (select review_policy_version::text from app.task_reviews where decision = 'accepted')),
  ('final-workload-total', (select (assigned_count + in_progress_count + blocked_count + submitted_count)::text from app.employee_workload_state where employee_id = '77777777-e000-4000-8000-000000000002')),
  ('linked-file-checksum', (select encode(file.content_sha256, 'hex') from app.submission_files as linked join app.private_files as file on file.company_id = linked.company_id and file.id = linked.file_id where linked.company_id = '11111111-1111-4111-8111-111111111111'));

select is((select observed from employee_results where label = 'initial-status'), 'assigned', 'a human-owned committed task starts assigned');
select is((select observed from employee_results where label = 'brief-bound'), '1', 'the task binds one exact employee brief version');
select is((select observed from employee_results where label = 'initial-workload'), '1', 'assignment updates operational workload immediately');
select is((select observed from employee_results where label = 'self-review-rejected'), 'true', 'self-review requires an explicit deterministic rule');
select is((select observed from employee_results where label = 'policy-one-version'), '2', 'manager replaces the committed task default with exact review policy version two');
select is((select observed from employee_results where label = 'policy-one-task-version'), '2', 'review policy changes advance the task version');
select is((select observed from employee_results where label = 'owner-task-count'), '1', 'owner can read the authorised task');
select is((select observed from employee_results where label = 'owner-brief-count'), '1', 'owner can read the separately approved brief');
select is((select observed from employee_results where label = 'bystander-task-count'), '0', 'unscoped managers cannot read confidential tasks');
select is((select observed from employee_results where label = 'bystander-brief-count'), '0', 'unscoped managers cannot read committed employee briefs');
select is((select observed from employee_results where label = 'ack-status'), 'acknowledged', 'owner acknowledges the exact task version');
select is((select observed from employee_results where label = 'ack-replayed'), 'true', 'identical acknowledgement retries replay');
select is((select observed from employee_results where label = 'idempotency-conflict'), 'true', 'conflicting idempotency reuse is rejected');
select is((select observed from employee_results where label = 'start-status'), 'in_progress', 'acknowledged work can start');
select is((select observed from employee_results where label = 'owner-correction-count'), '1', 'owner can read their private skill correction');
select is((select observed from employee_results where label = 'reviewer-correction-count'), '0', 'task reviewer cannot read private correction detail');
select is((select observed from employee_results where label = 'flag-event-safe'), 'false', 'general task event omits private correction detail');
select is((select observed from employee_results where label = 'pending-file-rejected'), 'true', 'pending files cannot be submitted');
select is((select observed from employee_results where label = 'invalid-scan-rejected'), 'true', 'scanner rejects mismatched MIME evidence');
select is((select observed from employee_results where label = 'clean-scan-state'), 'available', 'matching scan evidence releases a private file');
select is((select observed from employee_results where label = 'bystander-file-count'), '0', 'unscoped manager cannot read a private submission file');
select is((select observed from employee_results where label = 'submission-one-version'), '1', 'owner creates submission version one');
select is((select observed from employee_results where label = 'submission-one-replay'), 'true', 'identical submission retries replay');
select is((select observed from employee_results where label = 'policy-two-version'), '3', 'later reviewer assignment creates policy version three');
select is((select observed from employee_results where label = 'new-reviewer-v1-rejected'), 'true', 'new reviewer cannot review a submission bound to the old policy');
select is((select observed from employee_results where label = 'bound-reviewer-submission-count'), '1', 'original reviewer retains exact submitted-version access');
select is((select observed from employee_results where label = 'wrong-digest-rejected'), 'true', 'review rejects the wrong submission digest');
select is((select observed from employee_results where label = 'revision-status'), 'revision_requested', 'bound reviewer can request a revision');
select is((select observed from employee_results where label = 'profile-after-revision'), '1', 'revision request does not increase accepted profile evidence');
select is((select observed from employee_results where label = 'first-evidence-state'), 'disputed', 'revision request disputes provisional familiarity evidence');
select is((select observed from employee_results where label = 'submission-two-version'), '2', 'owner creates a new version after correction');
select is((select observed from employee_results where label = 'old-reviewer-v2-rejected'), 'true', 'old reviewer cannot review the new policy-bound version');
select is((select observed from employee_results where label = 'accepted-status'), 'accepted', 'required reviewer accepts the exact second version');
select is((select observed from employee_results where label = 'profile-after-acceptance'), '2', 'acceptance increments only the submitting profile once');
select is((select observed from employee_results where label = 'accepted-owner-evidence'), '1', 'acceptance creates one accepted contribution for the owner');
select is((select observed from employee_results where label = 'accepted-other-evidence'), '0', 'acceptance never updates another employee evidence profile');
select is((select observed from employee_results where label = 'accepted-effort-minutes'), '45', 'accepted effort retains the employee-reported observation');
select is((select observed from employee_results where label = 'review-policy-version'), '3', 'review records the exact policy version used');
select is((select observed from employee_results where label = 'final-workload-total'), '0', 'accepted work leaves no active workload counters');
select is((select observed from employee_results where label = 'linked-file-checksum'), repeat('34', 32), 'submission retains the scanner-recorded checksum');
select is((select observed from employee_results where label = 'bystander-correction-count'), '0', 'unscoped managers cannot read employee corrections');

select * from finish();
rollback;
