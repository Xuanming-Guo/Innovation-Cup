begin;
select plan(7);

insert into auth.users (id, instance_id, aud, role, email, encrypted_password, created_at, updated_at)
values
  (
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
    '00000000-0000-0000-0000-000000000000',
    'authenticated',
    'authenticated',
    'manager-a@example.invalid',
    extensions.crypt('local-test-only', extensions.gen_salt('bf')),
    clock_timestamp(),
    clock_timestamp()
  ),
  (
    'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
    '00000000-0000-0000-0000-000000000000',
    'authenticated',
    'authenticated',
    'manager-b@example.invalid',
    extensions.crypt('local-test-only', extensions.gen_salt('bf')),
    clock_timestamp(),
    clock_timestamp()
  )
on conflict (id) do nothing;

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values
  (
    'aaaaaaaa-0000-4000-8000-000000000001',
    '11111111-1111-4111-8111-111111111111',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
    'active',
    'company_admin',
    clock_timestamp()
  ),
  (
    'bbbbbbbb-0000-4000-8000-000000000002',
    '22222222-2222-4222-8222-222222222222',
    'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
    'active',
    'company_admin',
    clock_timestamp()
  );

insert into app.employee_profiles (id, company_id, membership_id)
values
  (
    'aaaaaaaa-1000-4000-8000-000000000001',
    '11111111-1111-4111-8111-111111111111',
    'aaaaaaaa-0000-4000-8000-000000000001'
  ),
  (
    'bbbbbbbb-1000-4000-8000-000000000002',
    '22222222-2222-4222-8222-222222222222',
    'bbbbbbbb-0000-4000-8000-000000000002'
  );

insert into app.teams (id, company_id, name)
values
  ('aaaaaaaa-2000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111', 'Alpha'),
  ('bbbbbbbb-2000-4000-8000-000000000002', '22222222-2222-4222-8222-222222222222', 'Beta');

create temporary table tenant_test_results (
  label text primary key,
  observed text not null
) on commit drop;
grant insert, select on table tenant_test_results to coordination_api;

set local role coordination_api;
insert into tenant_test_results (label, observed)
values ('missing-context-companies', (select count(*)::text from app.companies));
reset role;

select is(
  (select observed from tenant_test_results where label = 'missing-context-companies'),
  '0',
  'missing request context fails closed'
);

set local role coordination_api;
select set_config('app.actor_id', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:tenant-isolation', true);

insert into tenant_test_results (label, observed)
values
  ('company-count', (select count(*)::text from app.companies)),
  ('team-count', (select count(*)::text from app.teams)),
  (
    'cross-company-team-count',
    (
      select count(*)::text
      from app.teams
      where company_id = '22222222-2222-4222-8222-222222222222'
    )
  ),
  (
    'administrative-role',
    (
      select administrative_role
      from app.company_memberships
      where user_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'
    )
  );
reset role;

select is(
  (select observed from tenant_test_results where label = 'company-count'),
  '1',
  'actor sees only the current company'
);
select is(
  (select observed from tenant_test_results where label = 'team-count'),
  '1',
  'actor sees only current-company teams'
);
select is(
  (select observed from tenant_test_results where label = 'cross-company-team-count'),
  '0',
  'cross-company team read returns no rows'
);
select is(
  (select observed from tenant_test_results where label = 'administrative-role'),
  'company_admin',
  'administrative role comes from the membership record'
);

select throws_ok(
  $$
    insert into app.team_memberships (company_id, team_id, employee_id)
    values (
      '11111111-1111-4111-8111-111111111111',
      'aaaaaaaa-2000-4000-8000-000000000001',
      'bbbbbbbb-1000-4000-8000-000000000002'
    )
  $$,
  '23503',
  null,
  'composite foreign keys reject cross-company references'
);

update app.company_memberships
set membership_status = 'revoked'
where id = 'aaaaaaaa-0000-4000-8000-000000000001';

set local role coordination_api;
select set_config('app.actor_id', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:revoked-membership', true);
insert into tenant_test_results (label, observed)
values ('revoked-company-count', (select count(*)::text from app.companies));
reset role;

select is(
  (select observed from tenant_test_results where label = 'revoked-company-count'),
  '0',
  'revoked membership fails immediately'
);

select * from finish();
rollback;
