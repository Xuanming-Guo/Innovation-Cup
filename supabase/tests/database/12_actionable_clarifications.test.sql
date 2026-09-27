begin;
select plan(3);

insert into auth.users (
  id, instance_id, aud, role, email, encrypted_password, created_at, updated_at
) values (
  '12121212-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
  '00000000-0000-0000-0000-000000000000',
  'authenticated', 'authenticated', 'clarification-guard@example.invalid',
  extensions.crypt('local-test-only', extensions.gen_salt('bf')),
  clock_timestamp(), clock_timestamp()
);

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values (
  '12121212-0000-4000-8000-000000000011',
  '11111111-1111-4111-8111-111111111111',
  '12121212-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
  'active', 'manager', clock_timestamp()
);

insert into app.planning_requests (
  id, company_id, requester_membership_id, original_prompt,
  idempotency_key, request_digest
) values (
  '12121212-4000-4000-8000-000000000011',
  '11111111-1111-4111-8111-111111111111',
  '12121212-0000-4000-8000-000000000011',
  'Test the clarification invariant.',
  'clarification-guard-request', decode(repeat('12', 32), 'hex')
);

insert into app.retrieval_runs (
  id, company_id, request_id, actor_membership_id, purpose, allowed_scope,
  selected_manifest, omitted_manifest, missing_manifest, projection_digest,
  projection_characters, status, started_at, completed_at
) values (
  '12121212-5000-4000-8000-000000000011',
  '11111111-1111-4111-8111-111111111111',
  '12121212-4000-4000-8000-000000000011',
  '12121212-0000-4000-8000-000000000011',
  'test', '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
  decode(repeat('23', 32), 'hex'), 100, 'complete',
  clock_timestamp(), clock_timestamp()
);

insert into app.interpretation_runs (
  id, company_id, request_id, retrieval_run_id, model_id, model_version,
  sdk_version, prompt_version, schema_version, safety_profile, configuration,
  status, outcome, latency_ms, started_at, completed_at
) values (
  '12121212-6000-4000-8000-000000000011',
  '11111111-1111-4111-8111-111111111111',
  '12121212-4000-4000-8000-000000000011',
  '12121212-5000-4000-8000-000000000011',
  'gemini-test', 'gemini-test-001', '2.23.0', 'interpretation-v2',
  'candidate-task-contract.v1', 'provider-default-no-tools-v1', '{}'::jsonb,
  'completed', 'clarification_required', 10, clock_timestamp(), clock_timestamp()
);

select throws_ok(
  $$
    insert into app.candidate_contracts (
      id, company_id, request_id, interpretation_run_id, contract_json,
      contract_digest, admission_status, validation_issues
    ) values (
      '12121212-7000-4000-8000-000000000011',
      '11111111-1111-4111-8111-111111111111',
      '12121212-4000-4000-8000-000000000011',
      '12121212-6000-4000-8000-000000000011',
      '{"schema_version":"candidate-task-contract.v1"}'::jsonb,
      decode(repeat('34', 32), 'hex'), 'clarification_required',
      '[{"code":"material_assumption","path":"assumptions[0]","message":"confirmation required","disposition":"clarify"}]'::jsonb
    );
    set constraints all immediate;
  $$,
  '23514',
  'clarification_required_candidate_has_no_blocking_question',
  'a clarification-required candidate cannot commit without a blocking question'
);

select lives_ok(
  $$
    set constraints all deferred;
    insert into app.candidate_contracts (
      id, company_id, request_id, interpretation_run_id, contract_json,
      contract_digest, admission_status, validation_issues
    ) values (
      '12121212-7000-4000-8000-000000000012',
      '11111111-1111-4111-8111-111111111111',
      '12121212-4000-4000-8000-000000000011',
      '12121212-6000-4000-8000-000000000011',
      '{"schema_version":"candidate-task-contract.v1"}'::jsonb,
      decode(repeat('45', 32), 'hex'), 'clarification_required',
      '[{"code":"material_assumption","path":"assumptions[0]","message":"confirmation required","disposition":"clarify"}]'::jsonb
    );
    insert into app.clarification_questions (
      company_id, request_id, candidate_contract_id, question_key,
      category, question, blocks_planning, related_task_keys
    ) values (
      '11111111-1111-4111-8111-111111111111',
      '12121212-4000-4000-8000-000000000011',
      '12121212-7000-4000-8000-000000000012',
      'admission_1_test', 'authority',
      'Confirm or correct the material assumption.', true, '[]'::jsonb
    );
    set constraints all immediate;
  $$,
  'a candidate and its blocking manager action commit atomically'
);

select is(
  (
    select count(*)::integer
    from app.clarification_questions
    where candidate_contract_id = '12121212-7000-4000-8000-000000000012'
      and blocks_planning
  ),
  1,
  'the committed candidate exposes its blocking manager action'
);

select * from finish();
rollback;
