begin;
select plan(19);

select has_table(
  'app', 'company_ai_provider_configurations',
  'company AI provider metadata exists'
);
select has_function(
  'app', 'configure_company_gemini_credential',
  array['text', 'bytea', 'text', 'uuid'],
  'company Gemini configuration has one guarded write function'
);
select ok(
  not has_table_privilege(
    'coordination_api', 'app.company_ai_provider_configurations', 'SELECT'
  ),
  'API role cannot read provider metadata directly'
);
select ok(
  not has_table_privilege(
    'coordination_worker', 'app.company_ai_provider_configurations', 'SELECT'
  ),
  'worker role cannot read provider metadata directly'
);

insert into auth.users (
  id, instance_id, aud, role, email, encrypted_password, created_at, updated_at
) values
  ('99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa1', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'byok-admin@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp()),
  ('99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa2', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'byok-manager@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp()),
  ('99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa3', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'byok-other-admin@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp());

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values
  ('99999999-0000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
   '99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa1', 'active', 'company_admin', clock_timestamp()),
  ('99999999-0000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
   '99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa2', 'active', 'manager', clock_timestamp()),
  ('99999999-0000-4000-8000-000000000003', '22222222-2222-4222-8222-222222222222',
   '99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa3', 'active', 'company_admin', clock_timestamp());

create temporary table byok_results (
  label text primary key,
  observed text not null
) on commit drop;
grant insert, select, update on table byok_results to coordination_api, coordination_worker;

set local role coordination_api;
select set_config('app.actor_id', '99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:byok-configure', true);
insert into byok_results values (
  'configured-status',
  (select status from app.configure_company_gemini_credential(
    'test-company-gemini-key-value-0001',
    decode(repeat('a1', 32), 'hex'),
    'gemini-test',
    '99999999-c000-4000-8000-000000000001'
  ))
);
insert into byok_results values (
  'credential-hint',
  (select credential_hint from app.get_company_gemini_configuration())
);
reset role;

select is(
  (select observed from byok_results where label = 'configured-status'),
  'configured',
  'company administrator can configure a verified credential'
);
select is(
  (select observed from byok_results where label = 'credential-hint'),
  'a1a1a1a1a1a1',
  'administrator receives only a non-secret fingerprint hint'
);
select is(
  (select count(*)::integer from vault.secrets
   where name = 'coordination-gemini-11111111-1111-4111-8111-111111111111'),
  1,
  'plaintext credential is stored once in Vault'
);
select is(
  (select count(*)::integer from app.audit_events
   where event_type = 'ai_provider.gemini.configured'
     and company_id = '11111111-1111-4111-8111-111111111111'),
  1,
  'configuration creates a non-secret audit event'
);

set local role coordination_worker;
select set_config('app.actor_id', '99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:byok-resolve', true);
insert into byok_results values (
  'resolved-key', app.resolve_company_gemini_api_key()
);
reset role;

select is(
  (select observed from byok_results where label = 'resolved-key'),
  'test-company-gemini-key-value-0001',
  'worker resolves the current company key under active company context'
);

set local role coordination_api;
select set_config('app.actor_id', '99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa2', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:byok-manager-denied', true);
do $$
begin
  begin
    perform * from app.get_company_gemini_configuration();
    insert into byok_results values ('manager-read-denied', 'false');
  exception when insufficient_privilege then
    insert into byok_results values ('manager-read-denied', 'true');
  end;
  begin
    perform * from app.configure_company_gemini_credential(
      'test-company-gemini-key-value-denied',
      decode(repeat('d1', 32), 'hex'),
      'gemini-test',
      '99999999-c000-4000-8000-000000000002'
    );
    insert into byok_results values ('manager-write-denied', 'false');
  exception when insufficient_privilege then
    insert into byok_results values ('manager-write-denied', 'true');
  end;
end
$$;
reset role;

select is(
  (select observed from byok_results where label = 'manager-read-denied'),
  'true',
  'non-admin manager cannot inspect credential metadata'
);
select is(
  (select observed from byok_results where label = 'manager-write-denied'),
  'true',
  'non-admin manager cannot replace the company credential'
);
select ok(
  not has_function_privilege(
    'coordination_api', 'app.resolve_company_gemini_api_key()', 'EXECUTE'
  ),
  'API role cannot execute the plaintext resolver'
);

set local role coordination_api;
select set_config('app.actor_id', '99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa3', true);
select set_config('app.company_id', '22222222-2222-4222-8222-222222222222', true);
select set_config('app.purpose', 'test:byok-other-company', true);
insert into byok_results values (
  'other-company-status',
  (select status from app.get_company_gemini_configuration())
);
reset role;

select is(
  (select observed from byok_results where label = 'other-company-status'),
  'not_configured',
  'another company cannot observe the configured tenant'
);

set local role coordination_api;
select set_config('app.actor_id', '99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:byok-rotate', true);
select * from app.configure_company_gemini_credential(
  'test-company-gemini-key-value-0002',
  decode(repeat('a2', 32), 'hex'),
  'gemini-test',
  '99999999-c000-4000-8000-000000000003'
);
reset role;

select is(
  (select count(*)::integer from vault.secrets
   where name = 'coordination-gemini-11111111-1111-4111-8111-111111111111'),
  1,
  'rotation updates the existing Vault entry instead of accumulating keys'
);
select is(
  (select decrypted_secret from vault.decrypted_secrets
   where name = 'coordination-gemini-11111111-1111-4111-8111-111111111111'),
  'test-company-gemini-key-value-0002',
  'rotation replaces the encrypted credential value'
);

set local role coordination_api;
select set_config('app.actor_id', '99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:byok-remove', true);
insert into byok_results values (
  'removed-status',
  (select status from app.remove_company_gemini_credential(
    '99999999-c000-4000-8000-000000000004'
  ))
);
reset role;

select is(
  (select observed from byok_results where label = 'removed-status'),
  'not_configured',
  'administrator can remove the company credential'
);
select is(
  (select count(*)::integer from vault.secrets
   where name = 'coordination-gemini-11111111-1111-4111-8111-111111111111'),
  0,
  'removal deletes the Vault secret'
);

set local role coordination_api;
select set_config('app.actor_id', '99999999-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:byok-reset', true);
select * from app.configure_company_gemini_credential(
  'test-company-gemini-key-value-reset',
  decode(repeat('a3', 32), 'hex'),
  'gemini-test',
  '99999999-c000-4000-8000-000000000005'
);
reset role;

select lives_ok(
  $$select app_private.reset_demo_company('11111111-1111-4111-8111-111111111111')$$,
  'guarded demo reset succeeds when a company credential exists'
);
select is(
  (select count(*)::integer from vault.secrets
   where name = 'coordination-gemini-11111111-1111-4111-8111-111111111111'),
  0,
  'guarded demo reset removes the Vault secret'
);

select * from finish();
rollback;
