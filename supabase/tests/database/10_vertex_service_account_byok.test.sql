begin;
select plan(19);

select has_function(
  'app', 'configure_company_ai_credential',
  array['text', 'text', 'text', 'bytea', 'text', 'text', 'text', 'text', 'uuid'],
  'Google AI configuration has one guarded multi-mode write function'
);
select ok(
  not has_function_privilege(
    'coordination_api', 'app.resolve_company_ai_credential()', 'EXECUTE'
  ),
  'API role cannot execute the plaintext multi-mode resolver'
);
select ok(
  has_function_privilege(
    'coordination_worker', 'app.resolve_company_ai_credential()', 'EXECUTE'
  ),
  'worker role can execute the guarded multi-mode resolver'
);

insert into auth.users (
  id, instance_id, aud, role, email, encrypted_password, created_at, updated_at
) values
  ('aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa1', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'vertex-admin@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp()),
  ('aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa2', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'vertex-manager@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp()),
  ('aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa3', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'vertex-other-admin@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp());

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values
  ('aaaaaaaa-0000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
   'aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa1', 'active', 'company_admin', clock_timestamp()),
  ('aaaaaaaa-0000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
   'aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa2', 'active', 'manager', clock_timestamp()),
  ('aaaaaaaa-0000-4000-8000-000000000003', '22222222-2222-4222-8222-222222222222',
   'aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa3', 'active', 'company_admin', clock_timestamp());

create temporary table vertex_results (
  label text primary key,
  observed text not null
) on commit drop;
grant insert, select, update on table vertex_results to coordination_api, coordination_worker;

set local role coordination_api;
select set_config('app.actor_id', 'aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:vertex-configure', true);
select app.record_company_ai_credential_test(
  'vertex_ai', 'vertex_service_account', 'accepted', 'gemini-test',
  'aaaaaaaa-c000-4000-8000-000000000001'
);
select app.record_company_ai_credential_test(
  'vertex_ai', 'vertex_service_account', 'rejected', null,
  'aaaaaaaa-c000-4000-8000-000000000005'
);
select app.record_company_ai_credential_test(
  'vertex_ai', 'vertex_service_account', 'unavailable', null,
  'aaaaaaaa-c000-4000-8000-000000000006'
);
insert into vertex_results
select 'configured-status', status
from app.configure_company_ai_credential(
  'vertex_ai',
  'vertex_service_account',
  jsonb_build_object(
    'type', 'service_account',
    'project_id', 'test-vertex-project',
    'client_email', 'test-agent@test-vertex-project.iam.gserviceaccount.com',
    'private_key', 'synthetic-test-value-never-used-for-authentication'
  )::text,
  decode(repeat('b1', 32), 'hex'),
  'gemini-test',
  'test-vertex-project',
  'test-agent@test-vertex-project.iam.gserviceaccount.com',
  'global',
  'aaaaaaaa-c000-4000-8000-000000000002'
);
insert into vertex_results
select 'configuration', concat_ws('|', provider, credential_kind, vertex_project_id)
from app.get_company_ai_configuration();
reset role;

select is(
  (select observed from vertex_results where label = 'configured-status'),
  'configured',
  'company administrator can configure a validated Vertex credential'
);
select is(
  (select observed from vertex_results where label = 'configuration'),
  'vertex_ai|vertex_service_account|test-vertex-project',
  'safe configuration metadata identifies the selected Vertex mode'
);
select is(
  (select vertex_client_email from app.company_ai_provider_configurations
   where company_id = '11111111-1111-4111-8111-111111111111'),
  'test-agent@test-vertex-project.iam.gserviceaccount.com',
  'service-account identity is stored as non-secret metadata'
);
select is(
  (select count(*)::integer from vault.secrets
   where name = 'coordination-gemini-11111111-1111-4111-8111-111111111111'),
  1,
  'Vertex JSON is stored once in Vault'
);
select is(
  (select string_agg(details ->> 'test_outcome', ',' order by details ->> 'test_outcome')
   from app.audit_events
   where event_type = 'ai_provider.google.tested'
     and details ->> 'credential_kind' = 'vertex_service_account'),
  'accepted,rejected,unavailable',
  'all credential test outcomes create non-secret audit events'
);
select is(
  (select count(*)::integer from app.audit_events
   where event_type = 'ai_provider.vertex.configured'
     and company_id = '11111111-1111-4111-8111-111111111111'),
  1,
  'Vertex configuration creates a non-secret audit event'
);

set local role coordination_worker;
select set_config('app.actor_id', 'aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:vertex-resolve', true);
insert into vertex_results
select 'worker-resolution', concat_ws(
  '|', credential_kind, vertex_project_id, (credential_secret::jsonb ->> 'private_key')
)
from app.resolve_company_ai_credential();
reset role;

select is(
  (select observed from vertex_results where label = 'worker-resolution'),
  'vertex_service_account|test-vertex-project|synthetic-test-value-never-used-for-authentication',
  'only the worker resolver receives the current tenant credential'
);

set local role coordination_api;
select set_config('app.actor_id', 'aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa2', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:vertex-manager-denied', true);
do $$
begin
  begin
    perform * from app.get_company_ai_configuration();
    insert into vertex_results values ('manager-denied', 'false');
  exception when insufficient_privilege then
    insert into vertex_results values ('manager-denied', 'true');
  end;
end
$$;
reset role;

select is(
  (select observed from vertex_results where label = 'manager-denied'),
  'true',
  'non-admin manager cannot inspect Google credential metadata'
);

set local role coordination_api;
select set_config('app.actor_id', 'aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa3', true);
select set_config('app.company_id', '22222222-2222-4222-8222-222222222222', true);
select set_config('app.purpose', 'test:vertex-other-company', true);
insert into vertex_results
select 'other-company-status', status from app.get_company_ai_configuration();
reset role;

select is(
  (select observed from vertex_results where label = 'other-company-status'),
  'not_configured',
  'another company cannot observe the configured tenant'
);

set local role coordination_api;
select set_config('app.actor_id', 'aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:vertex-rotate', true);
select * from app.configure_company_ai_credential(
  'gemini_developer_api', 'api_key', 'test-company-gemini-key-after-vertex',
  decode(repeat('b2', 32), 'hex'), 'gemini-test', null, null, null,
  'aaaaaaaa-c000-4000-8000-000000000003'
);
reset role;

select is(
  (select count(*)::integer from vault.secrets
   where name = 'coordination-gemini-11111111-1111-4111-8111-111111111111'),
  1,
  'switching modes updates the existing Vault entry'
);
select is(
  (select decrypted_secret from vault.decrypted_secrets
   where name = 'coordination-gemini-11111111-1111-4111-8111-111111111111'),
  'test-company-gemini-key-after-vertex',
  'switching modes replaces the Vault plaintext'
);
select is(
  (select credential_kind from app.company_ai_provider_configurations
   where company_id = '11111111-1111-4111-8111-111111111111'),
  'api_key',
  'mode switch updates credential metadata atomically'
);
select is(
  (select count(*)::integer from app.audit_events
   where event_type = 'ai_provider.gemini.rotated'
     and company_id = '11111111-1111-4111-8111-111111111111'),
  1,
  'mode switch is audited as credential rotation'
);

set local role coordination_api;
select set_config('app.actor_id', 'aaaaaaaa-bbbb-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:vertex-remove', true);
insert into vertex_results
select 'removed-status', status from app.remove_company_ai_credential(
  'aaaaaaaa-c000-4000-8000-000000000004'
);
reset role;

select is(
  (select observed from vertex_results where label = 'removed-status'),
  'not_configured',
  'administrator can remove the selected Google credential'
);
select is(
  (select count(*)::integer from vault.secrets
   where name = 'coordination-gemini-11111111-1111-4111-8111-111111111111'),
  0,
  'removal deletes the Vault secret'
);
select is(
  (select count(*)::integer from app.company_ai_provider_configurations
   where company_id = '11111111-1111-4111-8111-111111111111'),
  0,
  'removal deletes the provider metadata row'
);

select * from finish();
rollback;
