begin;
select plan(16);

insert into auth.users (id, instance_id, aud, role, email, encrypted_password, created_at, updated_at)
values
  (
    '11111111-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
    '00000000-0000-0000-0000-000000000000',
    'authenticated',
    'authenticated',
    'planner-a@example.invalid',
    extensions.crypt('local-test-only', extensions.gen_salt('bf')),
    clock_timestamp(),
    clock_timestamp()
  ),
  (
    '22222222-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
    '00000000-0000-0000-0000-000000000000',
    'authenticated',
    'authenticated',
    'planner-b@example.invalid',
    extensions.crypt('local-test-only', extensions.gen_salt('bf')),
    clock_timestamp(),
    clock_timestamp()
  ),
  (
    '33333333-cccc-4ccc-8ccc-ccccccccccc3',
    '00000000-0000-0000-0000-000000000000',
    'authenticated',
    'authenticated',
    'member-a@example.invalid',
    extensions.crypt('local-test-only', extensions.gen_salt('bf')),
    clock_timestamp(),
    clock_timestamp()
  );

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values
  (
    '11111111-0000-4000-8000-000000000011',
    '11111111-1111-4111-8111-111111111111',
    '11111111-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
    'active', 'manager', clock_timestamp()
  ),
  (
    '22222222-0000-4000-8000-000000000022',
    '22222222-2222-4222-8222-222222222222',
    '22222222-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
    'active', 'manager', clock_timestamp()
  ),
  (
    '33333333-0000-4000-8000-000000000033',
    '11111111-1111-4111-8111-111111111111',
    '33333333-cccc-4ccc-8ccc-ccccccccccc3',
    'active', 'member', clock_timestamp()
  );

insert into app.employee_profiles (id, company_id, membership_id)
values
  (
    '11111111-1000-4000-8000-000000000011',
    '11111111-1111-4111-8111-111111111111',
    '11111111-0000-4000-8000-000000000011'
  ),
  (
    '22222222-1000-4000-8000-000000000022',
    '22222222-2222-4222-8222-222222222222',
    '22222222-0000-4000-8000-000000000022'
  ),
  (
    '33333333-1000-4000-8000-000000000033',
    '11111111-1111-4111-8111-111111111111',
    '33333333-0000-4000-8000-000000000033'
  );

insert into app.source_records (
  id, company_id, uploaded_by_employee_id, source_kind, title, authority_status
) values
  (
    '11111111-2000-4000-8000-000000000011',
    '11111111-1111-4111-8111-111111111111',
    '11111111-1000-4000-8000-000000000011',
    'fixture', 'Authoritative A', 'authoritative'
  ),
  (
    '22222222-2000-4000-8000-000000000022',
    '22222222-2222-4222-8222-222222222222',
    '22222222-1000-4000-8000-000000000022',
    'fixture', 'Authoritative B', 'authoritative'
  );

insert into app.source_versions (
  id, company_id, source_id, content_sha256, retrieved_at, access_snapshot
) values
  (
    '11111111-3000-4000-8000-000000000011',
    '11111111-1111-4111-8111-111111111111',
    '11111111-2000-4000-8000-000000000011',
    decode(repeat('11', 32), 'hex'), clock_timestamp(), '{}'::jsonb
  ),
  (
    '22222222-3000-4000-8000-000000000022',
    '22222222-2222-4222-8222-222222222222',
    '22222222-2000-4000-8000-000000000022',
    decode(repeat('22', 32), 'hex'), clock_timestamp(), '{}'::jsonb
  );

update app.source_records
set current_version_id = case company_id
  when '11111111-1111-4111-8111-111111111111' then '11111111-3000-4000-8000-000000000011'::uuid
  else '22222222-3000-4000-8000-000000000022'::uuid
end
where id in (
  '11111111-2000-4000-8000-000000000011',
  '22222222-2000-4000-8000-000000000022'
);

insert into app.source_access_grants (
  company_id, source_id, principal_kind, access_type, authority_reference
) values
  (
    '11111111-1111-4111-8111-111111111111',
    '11111111-2000-4000-8000-000000000011',
    'company', 'read', 'test-authority-a'
  ),
  (
    '22222222-2222-4222-8222-222222222222',
    '22222222-2000-4000-8000-000000000022',
    'company', 'read', 'test-authority-b'
  );

insert into app.planning_requests (
  id, company_id, requester_membership_id, original_prompt, idempotency_key, request_digest
) values
  (
    '11111111-4000-4000-8000-000000000011',
    '11111111-1111-4111-8111-111111111111',
    '11111111-0000-4000-8000-000000000011',
    'Prepare the A guide.', 'owner-fixture-key-a', decode(repeat('aa', 32), 'hex')
  ),
  (
    '22222222-4000-4000-8000-000000000022',
    '22222222-2222-4222-8222-222222222222',
    '22222222-0000-4000-8000-000000000022',
    'Prepare the B guide.', 'owner-fixture-key-b', decode(repeat('bb', 32), 'hex')
  );

create temporary table interpretation_test_results (
  label text primary key,
  observed text not null
) on commit drop;
grant insert, select on table interpretation_test_results to coordination_api, coordination_worker;

set local role coordination_api;
select set_config('app.actor_id', '11111111-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:interpretation-manager', true);

insert into interpretation_test_results (label, observed)
values
  ('visible-request-count', (select count(*)::text from app.planning_requests)),
  (
    'cross-company-request-count',
    (
      select count(*)::text from app.planning_requests
      where company_id = '22222222-2222-4222-8222-222222222222'
    )
  );

insert into app.planning_requests (
  id, company_id, requester_membership_id, original_prompt, idempotency_key, request_digest
) values (
  '11111111-4000-4000-8000-000000000012',
  '11111111-1111-4111-8111-111111111111',
  '11111111-0000-4000-8000-000000000011',
  'Prepare another A guide.', 'runtime-fixture-key-a', decode(repeat('ac', 32), 'hex')
);

do $$
begin
  begin
    insert into app.interpretation_runs (
      id, company_id, request_id, retrieval_run_id, model_id, sdk_version,
      prompt_version, schema_version, safety_profile, configuration, status, started_at
    ) values (
      gen_random_uuid(),
      '11111111-1111-4111-8111-111111111111',
      '11111111-4000-4000-8000-000000000011',
      gen_random_uuid(),
      'forbidden', '0', '0', '0', '0', '{}'::jsonb, 'running', clock_timestamp()
    );
    insert into interpretation_test_results values ('api-run-insert-denied', 'false');
  exception when insufficient_privilege or foreign_key_violation then
    insert into interpretation_test_results values ('api-run-insert-denied', 'true');
  end;
end
$$;
reset role;

set local role coordination_api;
select set_config('app.actor_id', '33333333-cccc-4ccc-8ccc-ccccccccccc3', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:interpretation-member', true);
insert into interpretation_test_results (label, observed)
values ('member-request-count', (select count(*)::text from app.planning_requests));
reset role;

set local role coordination_worker;
select set_config('app.actor_id', '11111111-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:interpretation-worker', true);

insert into app.retrieval_runs (
  id, company_id, request_id, actor_membership_id, purpose, allowed_scope,
  selected_manifest, omitted_manifest, missing_manifest, projection_digest,
  projection_characters, status, started_at, completed_at
) values (
  '11111111-5000-4000-8000-000000000011',
  '11111111-1111-4111-8111-111111111111',
  '11111111-4000-4000-8000-000000000011',
  '11111111-0000-4000-8000-000000000011',
  'test', '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
  decode(repeat('cc', 32), 'hex'), 100, 'complete', clock_timestamp(), clock_timestamp()
);

insert into app.interpretation_runs (
  id, company_id, request_id, retrieval_run_id, model_id, model_version, sdk_version,
  prompt_version, schema_version, safety_profile, configuration, status, outcome,
  latency_ms, started_at, completed_at
) values (
  '11111111-6000-4000-8000-000000000011',
  '11111111-1111-4111-8111-111111111111',
  '11111111-4000-4000-8000-000000000011',
  '11111111-5000-4000-8000-000000000011',
  'gemini-test', 'gemini-test-001', '2.23.0', 'interpretation-v1',
  'candidate-task-contract.v1', 'provider-default-no-tools-v1',
  '{"retry_attempts": 2}'::jsonb, 'completed', 'admitted', 25,
  clock_timestamp(), clock_timestamp()
);

insert into app.candidate_contracts (
  id, company_id, request_id, interpretation_run_id, contract_json,
  contract_digest, admission_status, validation_issues
) values (
  '11111111-7000-4000-8000-000000000011',
  '11111111-1111-4111-8111-111111111111',
  '11111111-4000-4000-8000-000000000011',
  '11111111-6000-4000-8000-000000000011',
  '{"schema_version":"candidate-task-contract.v1"}'::jsonb,
  decode(repeat('dd', 32), 'hex'), 'admitted', '[]'::jsonb
);

insert into app.clarification_questions (
  id, company_id, request_id, candidate_contract_id, question_key,
  category, question, blocks_planning, related_task_keys
) values (
  '11111111-7100-4000-8000-000000000011',
  '11111111-1111-4111-8111-111111111111',
  '11111111-4000-4000-8000-000000000011',
  '11111111-7000-4000-8000-000000000011',
  'capacity_confirmation', 'missing_data',
  'Should the recorded capacity window be used?', true, '[]'::jsonb
);

update app.planning_requests
set status = 'clarification_required'
where company_id = '11111111-1111-4111-8111-111111111111'
  and id = '11111111-4000-4000-8000-000000000011';

insert into interpretation_test_results (label, observed)
values
  ('worker-run-count', (select count(*)::text from app.interpretation_runs)),
  (
    'configuration-has-no-api-key',
    (
      select (not (configuration ? 'api_key'))::text
      from app.interpretation_runs
      where id = '11111111-6000-4000-8000-000000000011'
    )
  );

do $$
begin
  begin
    update app.candidate_contracts
    set admission_status = 'rejected'
    where id = '11111111-7000-4000-8000-000000000011';
    insert into interpretation_test_results values ('candidate-update-denied', 'false');
  exception when insufficient_privilege then
    insert into interpretation_test_results values ('candidate-update-denied', 'true');
  end;
end
$$;
reset role;

set local role coordination_api;
select set_config('app.actor_id', '11111111-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:clarification-resume', true);

insert into interpretation_test_results (label, observed)
select 'clarification-first-created', result.created::text
from app.submit_planning_clarifications(
  '11111111-1111-4111-8111-111111111111',
  '11111111-4000-4000-8000-000000000011',
  1,
  '11111111-7000-4000-8000-000000000011',
  '{"capacity_confirmation":"Use the recorded capacity window."}'::jsonb,
  'clarification-test-key-0001',
  decode(repeat('ef', 32), 'hex'),
  '11111111-7200-4000-8000-000000000011'
) as result;

insert into interpretation_test_results (label, observed)
select 'clarification-replay-created', result.created::text
from app.submit_planning_clarifications(
  '11111111-1111-4111-8111-111111111111',
  '11111111-4000-4000-8000-000000000011',
  1,
  '11111111-7000-4000-8000-000000000011',
  '{"capacity_confirmation":"Use the recorded capacity window."}'::jsonb,
  'clarification-test-key-0001',
  decode(repeat('ef', 32), 'hex'),
  '11111111-7200-4000-8000-000000000011'
) as result;
reset role;

select is(
  (select observed from interpretation_test_results where label = 'visible-request-count'),
  '1',
  'manager sees only current-company planning requests'
);
select is(
  (select observed from interpretation_test_results where label = 'cross-company-request-count'),
  '0',
  'cross-company planning request is invisible'
);
select is(
  (select observed from interpretation_test_results where label = 'member-request-count'),
  '0',
  'ordinary member cannot read manager interpretation state'
);
select is(
  (select count(*)::integer from app.planning_requests where id = '11111111-4000-4000-8000-000000000012'),
  1,
  'API manager role can create a same-company request'
);
select is(
  (select observed from interpretation_test_results where label = 'api-run-insert-denied'),
  'true',
  'API role cannot forge interpretation-run records'
);
select is(
  (select observed from interpretation_test_results where label = 'worker-run-count'),
  '1',
  'worker role can persist an authorised model run'
);
select is(
  (select observed from interpretation_test_results where label = 'configuration-has-no-api-key'),
  'true',
  'model run configuration contains no API key'
);
select is(
  (select observed from interpretation_test_results where label = 'candidate-update-denied'),
  'true',
  'candidate contracts are immutable to the worker role'
);
select is(
  (
    select count(*)::integer
    from app.interpretation_runs
    where company_id = '22222222-2222-4222-8222-222222222222'
  ),
  0,
  'worker write stayed within the authorised tenant'
);
select is(
  (select observed from interpretation_test_results where label = 'clarification-first-created'),
  'true',
  'manager clarification answers create a derived request'
);
select is(
  (select observed from interpretation_test_results where label = 'clarification-replay-created'),
  'false',
  'an identical clarification command replays idempotently'
);
select is(
  (
    select status from app.planning_requests
    where id = '11111111-4000-4000-8000-000000000011'
  ),
  'clarification_answered',
  'the original request records that its clarifications were answered'
);
select is(
  (
    select status from app.clarification_questions
    where id = '11111111-7100-4000-8000-000000000011'
  ),
  'answered',
  'the answered clarification question is no longer open'
);
select is(
  (
    select answer from app.clarification_responses
    where clarification_question_id = '11111111-7100-4000-8000-000000000011'
  ),
  'Use the recorded capacity window.',
  'the immutable clarification response retains the manager answer'
);
select is(
  (
    select count(*)::integer
    from app.planning_requests
    where clarification_parent_request_id = '11111111-4000-4000-8000-000000000011'
      and clarification_parent_request_version = 1
      and clarification_parent_candidate_id = '11111111-7000-4000-8000-000000000011'
      and request_version = 2
      and status = 'pending_interpretation'
  ),
  1,
  'the resumed request is bound to the exact request version and candidate'
);
select is(
  (
    select count(*)::integer
    from app.audit_events
    where aggregate_id = '11111111-4000-4000-8000-000000000011'
      and event_type = 'planning.clarifications_answered'
      and outcome = 'accepted'
  ),
  1,
  'clarification resume emits one accepted audit event'
);

select * from finish();
rollback;
