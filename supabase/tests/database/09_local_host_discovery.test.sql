begin;
select plan(22);

select has_table('app', 'host_runtime_endpoints', 'private host endpoint lease table exists');
select has_function(
  'app',
  'heartbeat_host_runtime_endpoint',
  array['uuid', 'uuid', 'text', 'text', 'integer'],
  'API runtime can heartbeat one host endpoint'
);
select has_function(
  'public',
  'resolve_coordination_host',
  array['uuid'],
  'authenticated clients have a narrow endpoint resolver'
);
select ok(
  not has_table_privilege('coordination_api', 'app.host_runtime_endpoints', 'SELECT'),
  'API role cannot read endpoint rows directly'
);
select ok(
  not has_table_privilege('authenticated', 'app.host_runtime_endpoints', 'SELECT'),
  'authenticated users cannot read endpoint rows directly'
);
select ok(
  has_function_privilege(
    'coordination_api',
    'app.heartbeat_host_runtime_endpoint(uuid,uuid,text,text,integer)',
    'EXECUTE'
  ),
  'API role can execute the heartbeat function'
);
select ok(
  has_function_privilege(
    'authenticated', 'public.resolve_coordination_host(uuid)', 'EXECUTE'
  ),
  'authenticated users can execute the discovery function'
);
select ok(
  not has_function_privilege('anon', 'public.resolve_coordination_host(uuid)', 'EXECUTE'),
  'anonymous users cannot execute endpoint discovery'
);

insert into auth.users (
  id, instance_id, aud, role, email, encrypted_password, created_at, updated_at
) values
  ('99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb1', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'host-member@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp()),
  ('99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb2', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'host-other@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp());

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values
  ('99999999-0000-4000-8000-000000000011', '11111111-1111-4111-8111-111111111111',
   '99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb1', 'active', 'company_admin', clock_timestamp()),
  ('99999999-0000-4000-8000-000000000012', '22222222-2222-4222-8222-222222222222',
   '99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb2', 'active', 'company_admin', clock_timestamp());

create temporary table host_test_results (
  label text primary key,
  observed text not null
) on commit drop;
grant insert, select on table host_test_results to coordination_api, authenticated;

select throws_ok(
  $$
  set local role coordination_api;
  select * from app.heartbeat_host_runtime_endpoint(
    '11111111-1111-4111-8111-111111111111',
    '99999999-1000-4000-8000-000000000001',
    'https://first.trycloudflare.com',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    120
  )
  $$,
  '42501',
  'company administrator host context is required',
  'host publication fails closed without an administrator context'
);
select throws_ok(
  $$
  set local role coordination_api;
  select set_config('app.actor_id', '99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb2', true);
  select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
  select set_config('app.purpose', 'test:host-cross-company', true);
  select * from app.heartbeat_host_runtime_endpoint(
    '11111111-1111-4111-8111-111111111111',
    '99999999-1000-4000-8000-000000000001',
    'https://first.trycloudflare.com',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    120
  )
  $$,
  '42501',
  'company administrator host context is required',
  'an administrator from another company cannot publish the endpoint'
);
select set_config('app.actor_id', '99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:host-registration', true);
select * from app.heartbeat_host_runtime_endpoint(
  '11111111-1111-4111-8111-111111111111',
  '99999999-1000-4000-8000-000000000001',
  'https://first.trycloudflare.com',
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  120
);
reset role;
select pass('first host acquires the company lease');

set local role coordination_api;
select set_config('app.actor_id', '99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:host-rotation', true);
select * from app.heartbeat_host_runtime_endpoint(
  '11111111-1111-4111-8111-111111111111',
  '99999999-1000-4000-8000-000000000001',
  'https://rotated.trycloudflare.com',
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  120
);
reset role;
select pass('the same host can heartbeat and rotate its tunnel origin');

select throws_ok(
  $$
  set local role coordination_api;
  select set_config('app.actor_id', '99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb1', true);
  select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
  select set_config('app.purpose', 'test:host-conflict', true);
  select * from app.heartbeat_host_runtime_endpoint(
    '11111111-1111-4111-8111-111111111111',
    '99999999-1000-4000-8000-000000000002',
    'https://second.trycloudflare.com',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    120
  )
  $$,
  '55006',
  'another host holds the active company lease',
  'a second live host cannot take over the company endpoint'
);

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb1","role":"authenticated"}',
  true
);
insert into host_test_results values (
  'member-origin',
  coalesce(
    public.resolve_coordination_host('11111111-1111-4111-8111-111111111111'),
    '<null>'
  )
);
insert into host_test_results values (
  'other-company-origin',
  coalesce(
    public.resolve_coordination_host('22222222-2222-4222-8222-222222222222'),
    '<null>'
  )
);
reset role;
select is(
  (select observed from host_test_results where label = 'member-origin'),
  'https://rotated.trycloudflare.com',
  'an active company member resolves the current HTTPS origin'
);
select is(
  (select observed from host_test_results where label = 'other-company-origin'),
  '<null>',
  'a member cannot discover another company endpoint'
);

update app.host_runtime_endpoints
set last_heartbeat_at = clock_timestamp() - interval '121 seconds',
    expires_at = clock_timestamp() - interval '1 second'
where company_id = '11111111-1111-4111-8111-111111111111';

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb1","role":"authenticated"}',
  true
);
insert into host_test_results values (
  'expired-origin',
  coalesce(
    public.resolve_coordination_host('11111111-1111-4111-8111-111111111111'),
    '<null>'
  )
);
reset role;
select is(
  (select observed from host_test_results where label = 'expired-origin'),
  '<null>',
  'expired host leases are not discoverable'
);

set local role coordination_api;
select set_config('app.actor_id', '99999999-bbbb-4bbb-8bbb-bbbbbbbbbbb1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:host-takeover', true);
select * from app.heartbeat_host_runtime_endpoint(
  '11111111-1111-4111-8111-111111111111',
  '99999999-1000-4000-8000-000000000002',
  'https://second.trycloudflare.com',
  'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
  120
);
insert into host_test_results values (
  'previous-release',
  app.release_host_runtime_endpoint(
    '11111111-1111-4111-8111-111111111111',
    '99999999-1000-4000-8000-000000000001'
  )::text
);
insert into host_test_results values (
  'active-release',
  app.release_host_runtime_endpoint(
    '11111111-1111-4111-8111-111111111111',
    '99999999-1000-4000-8000-000000000002'
  )::text
);
reset role;
select pass('a new host can take over an expired lease');
select is(
  (select observed from host_test_results where label = 'previous-release'),
  'false',
  'a previous host cannot release the replacement lease'
);
select is(
  (select observed from host_test_results where label = 'active-release'),
  'true',
  'the active host can release its own lease'
);

select is(
  (select count(*)::integer from app.host_runtime_endpoints),
  0,
  'graceful release removes the active endpoint'
);
select ok(
  not has_function_privilege(
    'coordination_worker',
    'app.heartbeat_host_runtime_endpoint(uuid,uuid,text,text,integer)',
    'EXECUTE'
  ),
  'worker role cannot publish a host endpoint'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'app.heartbeat_host_runtime_endpoint(uuid,uuid,text,text,integer)',
    'EXECUTE'
  ),
  'authenticated users cannot publish host endpoints'
);

select * from finish();
rollback;
