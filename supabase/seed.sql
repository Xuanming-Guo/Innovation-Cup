-- Synthetic tenant anchors only. Local demo users are provisioned separately through Auth.
-- No password, real email address, customer record or hosted credential belongs here.

insert into app.companies (
  id,
  slug,
  name,
  default_timezone,
  default_locale,
  status,
  is_demo
) values
  (
    '11111111-1111-4111-8111-111111111111',
    'northstar-demo',
    'Northstar Demo Company',
    'Europe/London',
    'en-GB',
    'active',
    true
  ),
  (
    '22222222-2222-4222-8222-222222222222',
    'harbor-demo',
    'Harbor Demo Company',
    'America/Los_Angeles',
    'en-US',
    'active',
    true
  )
on conflict (id) do update
set name = excluded.name,
    default_timezone = excluded.default_timezone,
    default_locale = excluded.default_locale,
    status = 'active',
    is_demo = true;
