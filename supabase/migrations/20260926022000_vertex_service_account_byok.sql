-- Add Vertex AI service-account BYOK beside the existing Gemini Developer API key path.
-- Canonical credential material remains only in Vault and is resolvable only by the worker.

alter table app.company_ai_provider_configurations
  drop constraint company_ai_provider_configurations_provider_check;

alter table app.company_ai_provider_configurations
  add column credential_kind text not null default 'api_key',
  add column vertex_project_id text null,
  add column vertex_client_email text null,
  add column vertex_location text null,
  add constraint company_ai_provider_configurations_provider_check
    check (provider in ('gemini_developer_api', 'vertex_ai')),
  add constraint company_ai_provider_configurations_credential_kind_check
    check (credential_kind in ('api_key', 'vertex_service_account')),
  add constraint company_ai_provider_configurations_mode_check check (
    (
      provider = 'gemini_developer_api'
      and credential_kind = 'api_key'
      and vertex_project_id is null
      and vertex_client_email is null
      and vertex_location is null
    ) or (
      provider = 'vertex_ai'
      and credential_kind = 'vertex_service_account'
      and vertex_project_id is not null
      and vertex_client_email is not null
      and vertex_location is not null
      and vertex_project_id ~ '^[a-z][a-z0-9-]{4,28}[a-z0-9]$'
      and split_part(vertex_client_email, '@', 2) =
        vertex_project_id || '.iam.gserviceaccount.com'
      and split_part(vertex_client_email, '@', 1) ~ '^[a-z][a-z0-9-]{4,28}[a-z0-9]$'
      and vertex_location ~ '^(global|[a-z]+-[a-z]+[0-9])$'
    )
  );

create or replace function app.get_company_ai_configuration()
returns table (
  provider text,
  credential_kind text,
  status text,
  credential_hint text,
  validated_model text,
  vertex_project_id text,
  vertex_client_email text,
  vertex_location text,
  configured_at timestamptz,
  validated_at timestamptz,
  rotated_at timestamptz
)
language plpgsql
stable
security definer
set search_path = pg_catalog, app
as $$
declare
  v_company_id uuid := app.current_company_id();
begin
  if not app.request_context_present()
     or not app.is_company_admin(v_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'company_admin_required';
  end if;

  return query
  select configuration.provider, configuration.credential_kind, 'configured'::text,
         configuration.credential_hint, configuration.validated_model,
         configuration.vertex_project_id, configuration.vertex_client_email,
         configuration.vertex_location, configuration.configured_at,
         configuration.validated_at, configuration.rotated_at
  from app.company_ai_provider_configurations as configuration
  where configuration.company_id = v_company_id;

  if not found then
    return query select 'gemini_developer_api'::text, 'api_key'::text,
      'not_configured'::text, null::text, null::text, null::text, null::text,
      null::text, null::timestamptz, null::timestamptz, null::timestamptz;
  end if;
end
$$;

create or replace function app.record_company_ai_credential_test(
  p_provider text,
  p_credential_kind text,
  p_test_outcome text,
  p_validated_model text,
  p_correlation_id uuid
)
returns void
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_company_id uuid := app.current_company_id();
  v_membership_id uuid;
  v_policy_revision bigint;
begin
  if not app.request_context_present()
     or not app.is_company_admin(v_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'company_admin_required';
  end if;
  if p_provider is null
     or p_provider not in ('gemini_developer_api', 'vertex_ai')
     or p_credential_kind is null
     or p_credential_kind not in ('api_key', 'vertex_service_account')
     or p_test_outcome is null
     or p_test_outcome not in ('accepted', 'rejected', 'unavailable')
     or p_correlation_id is null
     or (p_validated_model is not null
       and length(btrim(p_validated_model)) not between 1 and 200) then
    raise exception using errcode = '22023', message = 'invalid_ai_credential_test';
  end if;

  select membership.id, company.policy_revision
  into strict v_membership_id, v_policy_revision
  from app.company_memberships as membership
  join app.companies as company on company.id = membership.company_id
  where membership.company_id = v_company_id
    and membership.user_id = app.current_actor_id()
    and membership.membership_status = 'active'
    and membership.administrative_role = 'company_admin';

  insert into app.audit_events (
    company_id, actor_membership_id, event_type, aggregate_type, aggregate_id,
    outcome, policy_revision, input_digest, output_digest, details, correlation_id
  ) values (
    v_company_id, v_membership_id, 'ai_provider.google.tested',
    'company_ai_provider', v_company_id,
    case when p_test_outcome = 'accepted' then 'accepted' else 'rejected' end,
    v_policy_revision, null, null,
    jsonb_strip_nulls(jsonb_build_object(
      'provider', p_provider,
      'credential_kind', p_credential_kind,
      'test_outcome', p_test_outcome,
      'validated_model', p_validated_model
    )),
    p_correlation_id
  );
end
$$;

create or replace function app.configure_company_ai_credential(
  p_provider text,
  p_credential_kind text,
  p_credential_secret text,
  p_credential_fingerprint bytea,
  p_validated_model text,
  p_vertex_project_id text,
  p_vertex_client_email text,
  p_vertex_location text,
  p_correlation_id uuid
)
returns table (
  provider text,
  credential_kind text,
  status text,
  credential_hint text,
  validated_model text,
  vertex_project_id text,
  vertex_client_email text,
  vertex_location text,
  configured_at timestamptz,
  validated_at timestamptz,
  rotated_at timestamptz
)
language plpgsql
security definer
set search_path = pg_catalog, app, vault
as $$
declare
  v_company_id uuid := app.current_company_id();
  v_membership_id uuid;
  v_policy_revision bigint;
  v_existing app.company_ai_provider_configurations%rowtype;
  v_secret_id uuid;
  v_secret_json jsonb;
  v_hint text := encode(substring(p_credential_fingerprint from 1 for 6), 'hex');
  v_is_api_key boolean := p_provider = 'gemini_developer_api'
    and p_credential_kind = 'api_key'
    and p_vertex_project_id is null
    and p_vertex_client_email is null
    and p_vertex_location is null;
  v_is_vertex boolean := p_provider = 'vertex_ai'
    and p_credential_kind = 'vertex_service_account'
    and p_vertex_project_id is not null
    and p_vertex_client_email is not null
    and p_vertex_location is not null;
begin
  if not app.request_context_present()
     or not app.is_company_admin(v_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'company_admin_required';
  end if;
  if p_credential_secret is null
     or length(p_credential_secret) not between 20 and 65536
     or p_credential_fingerprint is null
     or octet_length(p_credential_fingerprint) <> 32
     or p_validated_model is null
     or length(btrim(p_validated_model)) not between 1 and 200
     or p_correlation_id is null
     or not (coalesce(v_is_api_key, false) or coalesce(v_is_vertex, false)) then
    raise exception using errcode = '22023', message = 'invalid_ai_provider_configuration';
  end if;

  if v_is_vertex then
    begin
      v_secret_json := p_credential_secret::jsonb;
    exception when others then
      raise exception using errcode = '22023', message = 'invalid_ai_provider_configuration';
    end;
    if jsonb_typeof(v_secret_json) <> 'object'
       or v_secret_json ->> 'type' <> 'service_account'
       or v_secret_json ->> 'project_id' <> p_vertex_project_id
       or v_secret_json ->> 'client_email' <> p_vertex_client_email
       or p_vertex_project_id !~ '^[a-z][a-z0-9-]{4,28}[a-z0-9]$'
       or split_part(p_vertex_client_email, '@', 2) <>
         p_vertex_project_id || '.iam.gserviceaccount.com'
       or split_part(p_vertex_client_email, '@', 1) !~
         '^[a-z][a-z0-9-]{4,28}[a-z0-9]$'
       or p_vertex_location !~ '^(global|[a-z]+-[a-z]+[0-9])$' then
      raise exception using errcode = '22023', message = 'invalid_ai_provider_configuration';
    end if;
  end if;

  select membership.id, company.policy_revision
  into strict v_membership_id, v_policy_revision
  from app.company_memberships as membership
  join app.companies as company on company.id = membership.company_id
  where membership.company_id = v_company_id
    and membership.user_id = app.current_actor_id()
    and membership.membership_status = 'active'
    and membership.administrative_role = 'company_admin';

  select * into v_existing
  from app.company_ai_provider_configurations
  where company_id = v_company_id
  for update;

  if found
     and v_existing.provider = p_provider
     and v_existing.credential_kind = p_credential_kind
     and v_existing.credential_fingerprint = p_credential_fingerprint then
    update app.company_ai_provider_configurations
    set validated_model = btrim(p_validated_model),
        vertex_project_id = p_vertex_project_id,
        vertex_client_email = p_vertex_client_email,
        vertex_location = p_vertex_location,
        validated_at = clock_timestamp(),
        configured_by_membership_id = v_membership_id
    where company_id = v_company_id;
  else
    if v_existing.company_id is null then
      v_secret_id := vault.create_secret(
        p_credential_secret,
        'coordination-gemini-' || v_company_id::text,
        'Company-owned Google Gemini credential for Coordination Engine'
      );
      insert into app.company_ai_provider_configurations (
        company_id, provider, credential_kind, vault_secret_id,
        credential_fingerprint, credential_hint, validated_model,
        vertex_project_id, vertex_client_email, vertex_location,
        configured_by_membership_id
      ) values (
        v_company_id, p_provider, p_credential_kind, v_secret_id,
        p_credential_fingerprint, v_hint, btrim(p_validated_model),
        p_vertex_project_id, p_vertex_client_email, p_vertex_location,
        v_membership_id
      );
    else
      perform vault.update_secret(v_existing.vault_secret_id, p_credential_secret);
      update app.company_ai_provider_configurations
      set provider = p_provider,
          credential_kind = p_credential_kind,
          credential_fingerprint = p_credential_fingerprint,
          credential_hint = v_hint,
          validated_model = btrim(p_validated_model),
          vertex_project_id = p_vertex_project_id,
          vertex_client_email = p_vertex_client_email,
          vertex_location = p_vertex_location,
          configured_by_membership_id = v_membership_id,
          validated_at = clock_timestamp(),
          rotated_at = clock_timestamp()
      where company_id = v_company_id;
    end if;

    insert into app.audit_events (
      company_id, actor_membership_id, event_type, aggregate_type, aggregate_id,
      outcome, policy_revision, input_digest, output_digest, details, correlation_id
    ) values (
      v_company_id, v_membership_id,
      case
        when p_credential_kind = 'api_key' and v_existing.company_id is null
          then 'ai_provider.gemini.configured'
        when p_credential_kind = 'api_key'
          then 'ai_provider.gemini.rotated'
        when v_existing.company_id is null
          then 'ai_provider.vertex.configured'
        else 'ai_provider.vertex.rotated'
      end,
      'company_ai_provider', v_company_id, 'accepted', v_policy_revision,
      null, null, jsonb_strip_nulls(jsonb_build_object(
        'provider', p_provider,
        'credential_kind', p_credential_kind,
        'validated_model', btrim(p_validated_model),
        'vertex_project_id', p_vertex_project_id,
        'vertex_client_email', p_vertex_client_email,
        'vertex_location', p_vertex_location
      )), p_correlation_id
    );
  end if;

  return query select * from app.get_company_ai_configuration();
end
$$;

create or replace function app.remove_company_ai_credential(p_correlation_id uuid)
returns table (
  provider text,
  credential_kind text,
  status text,
  credential_hint text,
  validated_model text,
  vertex_project_id text,
  vertex_client_email text,
  vertex_location text,
  configured_at timestamptz,
  validated_at timestamptz,
  rotated_at timestamptz
)
language plpgsql
security definer
set search_path = pg_catalog, app, vault
as $$
declare
  v_company_id uuid := app.current_company_id();
  v_membership_id uuid;
  v_policy_revision bigint;
  v_existing app.company_ai_provider_configurations%rowtype;
begin
  if not app.request_context_present()
     or not app.is_company_admin(v_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'company_admin_required';
  end if;
  if p_correlation_id is null then
    raise exception using errcode = '22023', message = 'invalid_ai_provider_configuration';
  end if;

  select membership.id, company.policy_revision
  into strict v_membership_id, v_policy_revision
  from app.company_memberships as membership
  join app.companies as company on company.id = membership.company_id
  where membership.company_id = v_company_id
    and membership.user_id = app.current_actor_id()
    and membership.membership_status = 'active'
    and membership.administrative_role = 'company_admin';

  delete from app.company_ai_provider_configurations
  where company_id = v_company_id
  returning * into v_existing;

  if v_existing.vault_secret_id is not null then
    delete from vault.secrets where id = v_existing.vault_secret_id;
    insert into app.audit_events (
      company_id, actor_membership_id, event_type, aggregate_type, aggregate_id,
      outcome, policy_revision, input_digest, output_digest, details, correlation_id
    ) values (
      v_company_id, v_membership_id,
      case when v_existing.credential_kind = 'api_key'
        then 'ai_provider.gemini.removed'
        else 'ai_provider.vertex.removed' end,
      'company_ai_provider', v_company_id, 'accepted', v_policy_revision,
      null, null, jsonb_build_object(
        'provider', v_existing.provider,
        'credential_kind', v_existing.credential_kind
      ), p_correlation_id
    );
  end if;

  return query select * from app.get_company_ai_configuration();
end
$$;

create or replace function app.resolve_company_ai_credential()
returns table (
  provider text,
  credential_kind text,
  credential_secret text,
  validated_model text,
  vertex_project_id text,
  vertex_client_email text,
  vertex_location text
)
language plpgsql
stable
security definer
set search_path = pg_catalog, app, vault
as $$
declare
  v_company_id uuid := app.current_company_id();
begin
  if not app.request_context_present()
     or not app.has_active_membership(v_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'active_company_context_required';
  end if;

  return query
  select configuration.provider, configuration.credential_kind,
         secret.decrypted_secret, configuration.validated_model,
         configuration.vertex_project_id, configuration.vertex_client_email,
         configuration.vertex_location
  from app.company_ai_provider_configurations as configuration
  join vault.decrypted_secrets as secret on secret.id = configuration.vault_secret_id
  where configuration.company_id = v_company_id;

  if not found then
    raise exception using errcode = 'P0002', message = 'company_gemini_not_configured';
  end if;
end
$$;

-- Keep the original API-key functions as compatibility wrappers during a rolling deployment.
-- They intentionally cannot return a Vertex credential through the legacy resolver.
create or replace function app.get_company_gemini_configuration()
returns table (
  provider text,
  status text,
  credential_hint text,
  validated_model text,
  configured_at timestamptz,
  validated_at timestamptz,
  rotated_at timestamptz
)
language plpgsql
stable
security definer
set search_path = pg_catalog, app
as $$
begin
  return query
  select configuration.provider, configuration.status, configuration.credential_hint,
         configuration.validated_model, configuration.configured_at,
         configuration.validated_at, configuration.rotated_at
  from app.get_company_ai_configuration() as configuration
  where configuration.credential_kind = 'api_key';

  if not found then
    return query select 'gemini_developer_api'::text, 'not_configured'::text,
      null::text, null::text, null::timestamptz, null::timestamptz, null::timestamptz;
  end if;
end
$$;

create or replace function app.configure_company_gemini_credential(
  p_api_key text,
  p_credential_fingerprint bytea,
  p_validated_model text,
  p_correlation_id uuid
)
returns table (
  provider text,
  status text,
  credential_hint text,
  validated_model text,
  configured_at timestamptz,
  validated_at timestamptz,
  rotated_at timestamptz
)
language sql
security definer
set search_path = pg_catalog, app
as $$
  select configuration.provider, configuration.status, configuration.credential_hint,
         configuration.validated_model, configuration.configured_at,
         configuration.validated_at, configuration.rotated_at
  from app.configure_company_ai_credential(
    'gemini_developer_api', 'api_key', p_api_key, p_credential_fingerprint,
    p_validated_model, null, null, null, p_correlation_id
  ) as configuration
$$;

create or replace function app.remove_company_gemini_credential(p_correlation_id uuid)
returns table (
  provider text,
  status text,
  credential_hint text,
  validated_model text,
  configured_at timestamptz,
  validated_at timestamptz,
  rotated_at timestamptz
)
language sql
security definer
set search_path = pg_catalog, app
as $$
  select configuration.provider, configuration.status, configuration.credential_hint,
         configuration.validated_model, configuration.configured_at,
         configuration.validated_at, configuration.rotated_at
  from app.remove_company_ai_credential(p_correlation_id) as configuration
$$;

create or replace function app.resolve_company_gemini_api_key()
returns text
language plpgsql
stable
security definer
set search_path = pg_catalog, app
as $$
declare
  v_api_key text;
begin
  select credential.credential_secret into v_api_key
  from app.resolve_company_ai_credential() as credential
  where credential.credential_kind = 'api_key';

  if v_api_key is null then
    raise exception using errcode = 'P0002', message = 'company_gemini_not_configured';
  end if;
  return v_api_key;
end
$$;

revoke execute on function app.get_company_ai_configuration() from public;
revoke execute on function app.record_company_ai_credential_test(text, text, text, text, uuid)
  from public;
revoke execute on function app.configure_company_ai_credential(
  text, text, text, bytea, text, text, text, text, uuid
) from public;
revoke execute on function app.remove_company_ai_credential(uuid) from public;
revoke execute on function app.resolve_company_ai_credential() from public;

grant execute on function app.get_company_ai_configuration() to coordination_api;
grant execute on function app.record_company_ai_credential_test(text, text, text, text, uuid)
  to coordination_api;
grant execute on function app.configure_company_ai_credential(
  text, text, text, bytea, text, text, text, text, uuid
) to coordination_api;
grant execute on function app.remove_company_ai_credential(uuid) to coordination_api;
grant execute on function app.resolve_company_ai_credential() to coordination_worker;

insert into app_private.migration_contract (version, name)
values ('20260926022000', 'vertex_service_account_byok');
