begin;
select plan(9);

insert into auth.users (id, instance_id, aud, role, email, encrypted_password, created_at, updated_at)
values
  (
    'cccccccc-cccc-4ccc-8ccc-ccccccccccc3',
    '00000000-0000-0000-0000-000000000000',
    'authenticated',
    'authenticated',
    'uploader@example.invalid',
    extensions.crypt('local-test-only', extensions.gen_salt('bf')),
    clock_timestamp(),
    clock_timestamp()
  ),
  (
    'dddddddd-dddd-4ddd-8ddd-ddddddddddd4',
    '00000000-0000-0000-0000-000000000000',
    'authenticated',
    'authenticated',
    'outsider@example.invalid',
    extensions.crypt('local-test-only', extensions.gen_salt('bf')),
    clock_timestamp(),
    clock_timestamp()
  )
on conflict (id) do nothing;

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values
  (
    'cccccccc-0000-4000-8000-000000000003',
    '11111111-1111-4111-8111-111111111111',
    'cccccccc-cccc-4ccc-8ccc-ccccccccccc3',
    'active',
    'member',
    clock_timestamp()
  ),
  (
    'dddddddd-0000-4000-8000-000000000004',
    '22222222-2222-4222-8222-222222222222',
    'dddddddd-dddd-4ddd-8ddd-ddddddddddd4',
    'active',
    'member',
    clock_timestamp()
  );

insert into app.employee_profiles (id, company_id, membership_id)
values
  (
    'cccccccc-1000-4000-8000-000000000003',
    '11111111-1111-4111-8111-111111111111',
    'cccccccc-0000-4000-8000-000000000003'
  ),
  (
    'dddddddd-1000-4000-8000-000000000004',
    '22222222-2222-4222-8222-222222222222',
    'dddddddd-0000-4000-8000-000000000004'
  );

insert into app.employee_workload_state (
  company_id, employee_id, assigned_count
) values (
  '22222222-2222-4222-8222-222222222222',
  'dddddddd-1000-4000-8000-000000000004',
  1
);

insert into app.source_records (
  id, company_id, uploaded_by_employee_id, source_kind, title, authority_status
) values (
  'cccccccc-2000-4000-8000-000000000003',
  '11111111-1111-4111-8111-111111111111',
  'cccccccc-1000-4000-8000-000000000003',
  'upload',
  'Synthetic policy brief',
  'authoritative'
);

insert into app.source_access_grants (
  company_id, source_id, principal_kind, access_type, authority_reference
) values (
  '11111111-1111-4111-8111-111111111111',
  'cccccccc-2000-4000-8000-000000000003',
  'company',
  'read',
  'synthetic-test-authority'
);

set local role authenticated;
select set_config('request.jwt.claim.sub', 'cccccccc-cccc-4ccc-8ccc-ccccccccccc3', true);
select is(
  (
    select count(*)::integer
    from app.issue_private_storage_ticket(
      'create-upload',
      '11111111-1111-4111-8111-111111111111',
      'eeeeeeee-0000-4000-8000-000000000005',
      '11111111-1111-4111-8111-111111111111/eeeeeeee-0000-4000-8000-000000000005/payload.txt',
      'source',
      'cccccccc-2000-4000-8000-000000000003',
      'brief.txt',
      'text/plain',
      128
    )
  ),
  1,
  'authorised upload creates one scoped quarantine ticket'
);

select is(
  (
    select count(*)::integer
    from app.issue_private_storage_ticket(
      'create-upload',
      '22222222-2222-4222-8222-222222222222',
      'eeeeeeee-0000-4000-8000-000000000006',
      '22222222-2222-4222-8222-222222222222/eeeeeeee-0000-4000-8000-000000000006/payload.txt',
      'evidence',
      null,
      'brief.txt',
      'text/plain',
      128
    )
  ),
  0,
  'cross-company upload ticket fails closed'
);

select is(
  (
    select count(*)::integer
    from app.issue_private_storage_ticket(
      'create-download',
      '11111111-1111-4111-8111-111111111111',
      'eeeeeeee-0000-4000-8000-000000000005'
    )
  ),
  0,
  'pending upload cannot receive a download ticket'
);

select throws_ok(
  $$
    insert into storage.objects (bucket_id, name, owner_id)
    values (
      'coordination-quarantine',
      '11111111-1111-4111-8111-111111111111/attacker/payload.txt',
      'cccccccc-cccc-4ccc-8ccc-ccccccccccc3'
    )
  $$,
  '42501',
  null,
  'authenticated users cannot bypass signed upload issuance'
);
reset role;

update app.private_files
set state = 'available', bucket_id = 'coordination-private', scan_state = 'clean',
    scan_engine_version = 'fixture-scanner-v1',
    content_sha256 = decode(repeat('ab', 32), 'hex'),
    scanned_at = clock_timestamp(), detected_mime_type = declared_mime_type,
    object_path = '11111111-1111-4111-8111-111111111111/eeeeeeee-0000-4000-8000-000000000005/final/brief.txt'
where id = 'eeeeeeee-0000-4000-8000-000000000005';

set local role authenticated;
select set_config('request.jwt.claim.sub', 'cccccccc-cccc-4ccc-8ccc-ccccccccccc3', true);
select is(
  (
    select count(*)::integer
    from app.issue_private_storage_ticket(
      'create-download',
      '11111111-1111-4111-8111-111111111111',
      'eeeeeeee-0000-4000-8000-000000000005'
    )
  ),
  1,
  'current authorised uploader can obtain an available-file ticket'
);
reset role;

insert into app.companies (id, slug, name, is_demo)
values ('99999999-9999-4999-8999-999999999999', 'not-a-demo', 'Non-demo guard record', false);

select throws_ok(
  $$ select app_private.reset_demo_company('99999999-9999-4999-8999-999999999999') $$,
  '42501',
  'demo reset refused for non-demo or unknown company',
  'demo reset refuses a non-demo tenant'
);
select is(
  (select count(*)::integer from app.companies where id = '99999999-9999-4999-8999-999999999999'),
  1,
  'refused reset leaves non-demo tenant intact'
);

select lives_ok(
  $$ select app_private.reset_demo_company('22222222-2222-4222-8222-222222222222') $$,
  'demo reset accepts an explicitly marked demo tenant'
);
select is(
  (
    select count(*)::integer
    from app.employee_profiles
    where company_id = '22222222-2222-4222-8222-222222222222'
  ) + (
    select count(*)::integer
    from app.employee_workload_state
    where company_id = '22222222-2222-4222-8222-222222222222'
  ),
  0,
  'demo reset removes workload dependants before employee profiles'
);

select * from finish();
rollback;
