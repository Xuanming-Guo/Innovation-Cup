-- Company-owned Gemini credentials. Secret material lives only in Supabase Vault and is
-- retrievable only by the least-privileged durable worker under an active company context.

create extension if not exists supabase_vault with schema vault;

create table app.company_ai_provider_configurations (
  company_id uuid primary key references app.companies(id) on delete cascade,
  provider text not null default 'gemini_developer_api'
    check (provider = 'gemini_developer_api'),
  vault_secret_id uuid not null unique,
  credential_fingerprint bytea not null check (octet_length(credential_fingerprint) = 32),
  credential_hint text not null check (credential_hint ~ '^[0-9a-f]{12}$'),
  validated_model text not null check (length(btrim(validated_model)) between 1 and 200),
  configured_by_membership_id uuid not null,
  configured_at timestamptz not null default clock_timestamp(),
  validated_at timestamptz not null default clock_timestamp(),
  rotated_at timestamptz null,
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  foreign key (company_id, configured_by_membership_id)
    references app.company_memberships(company_id, id)
);

alter table app.company_ai_provider_configurations enable row level security;

-- No runtime table grants are intentional. API and worker access is limited to the
-- security-definer functions below, with plaintext retrieval granted only to the worker.
revoke all on table app.company_ai_provider_configurations
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;

create trigger company_ai_provider_configurations_touch_updated
  before update on app.company_ai_provider_configurations
  for each row execute function app.touch_updated_row();

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
declare
  v_company_id uuid := app.current_company_id();
begin
  if not app.request_context_present()
     or not app.is_company_admin(v_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'company_admin_required';
  end if;

  return query
  select configuration.provider, 'configured'::text, configuration.credential_hint,
         configuration.validated_model, configuration.configured_at,
         configuration.validated_at, configuration.rotated_at
  from app.company_ai_provider_configurations as configuration
  where configuration.company_id = v_company_id;

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
  v_hint text := encode(substring(p_credential_fingerprint from 1 for 6), 'hex');
begin
  if not app.request_context_present()
     or not app.is_company_admin(v_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'company_admin_required';
  end if;
  if length(p_api_key) not between 20 and 512
     or octet_length(p_credential_fingerprint) <> 32
     or length(btrim(p_validated_model)) not between 1 and 200 then
    raise exception using errcode = '22023', message = 'invalid_gemini_configuration';
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

  if found and v_existing.credential_fingerprint = p_credential_fingerprint then
    update app.company_ai_provider_configurations
    set validated_model = btrim(p_validated_model),
        validated_at = clock_timestamp(),
        configured_by_membership_id = v_membership_id
    where company_id = v_company_id;
  else
    if v_existing.company_id is null then
      v_secret_id := vault.create_secret(
        p_api_key,
        'coordination-gemini-' || v_company_id::text,
        'Company-owned Gemini credential for Coordination Engine'
      );
      insert into app.company_ai_provider_configurations (
        company_id, vault_secret_id, credential_fingerprint, credential_hint,
        validated_model, configured_by_membership_id
      ) values (
        v_company_id, v_secret_id, p_credential_fingerprint, v_hint,
        btrim(p_validated_model), v_membership_id
      );
    else
      perform vault.update_secret(v_existing.vault_secret_id, p_api_key);
      update app.company_ai_provider_configurations
      set credential_fingerprint = p_credential_fingerprint,
          credential_hint = v_hint,
          validated_model = btrim(p_validated_model),
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
      case when v_existing.company_id is null
        then 'ai_provider.gemini.configured'
        else 'ai_provider.gemini.rotated' end,
      'company_ai_provider', v_company_id, 'accepted', v_policy_revision,
      null, null, jsonb_build_object(
        'provider', 'gemini_developer_api',
        'validated_model', btrim(p_validated_model)
      ), p_correlation_id
    );
  end if;

  return query select * from app.get_company_gemini_configuration();
end
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
language plpgsql
security definer
set search_path = pg_catalog, app, vault
as $$
declare
  v_company_id uuid := app.current_company_id();
  v_membership_id uuid;
  v_policy_revision bigint;
  v_secret_id uuid;
begin
  if not app.request_context_present()
     or not app.is_company_admin(v_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'company_admin_required';
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
  returning vault_secret_id into v_secret_id;

  if v_secret_id is not null then
    delete from vault.secrets where id = v_secret_id;
    insert into app.audit_events (
      company_id, actor_membership_id, event_type, aggregate_type, aggregate_id,
      outcome, policy_revision, input_digest, output_digest, details, correlation_id
    ) values (
      v_company_id, v_membership_id, 'ai_provider.gemini.removed',
      'company_ai_provider', v_company_id, 'accepted', v_policy_revision,
      null, null, jsonb_build_object('provider', 'gemini_developer_api'), p_correlation_id
    );
  end if;

  return query select * from app.get_company_gemini_configuration();
end
$$;

create or replace function app.resolve_company_gemini_api_key()
returns text
language plpgsql
stable
security definer
set search_path = pg_catalog, app, vault
as $$
declare
  v_company_id uuid := app.current_company_id();
  v_api_key text;
begin
  if not app.request_context_present()
     or not app.has_active_membership(v_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'active_company_context_required';
  end if;

  select secret.decrypted_secret into v_api_key
  from app.company_ai_provider_configurations as configuration
  join vault.decrypted_secrets as secret on secret.id = configuration.vault_secret_id
  where configuration.company_id = v_company_id;

  if v_api_key is null then
    raise exception using errcode = 'P0002', message = 'company_gemini_not_configured';
  end if;
  return v_api_key;
end
$$;

create or replace function app.cleanup_company_gemini_secret()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app, vault
as $$
declare
  v_secret_id uuid;
begin
  select vault_secret_id into v_secret_id
  from app.company_ai_provider_configurations
  where company_id = old.id;
  if v_secret_id is not null then
    delete from vault.secrets where id = v_secret_id;
  end if;
  return old;
end
$$;

create trigger companies_cleanup_gemini_secret
  before delete on app.companies
  for each row execute function app.cleanup_company_gemini_secret();

-- The guarded demo reset predates BYOK. Wrap it so a configured demo key cannot block
-- membership deletion and never leaves an orphaned Vault secret.
alter function app_private.reset_demo_company(uuid)
  rename to reset_demo_company_without_ai_provider;

create or replace function app_private.reset_demo_company(p_company_id uuid)
returns void
language plpgsql
security definer
set search_path = pg_catalog, app, app_private, vault
as $$
declare
  v_secret_id uuid;
begin
  if not exists (
    select 1 from app.companies where id = p_company_id and is_demo is true
  ) then
    raise exception 'demo reset refused for non-demo or unknown company'
      using errcode = '42501';
  end if;

  delete from app.company_ai_provider_configurations
  where company_id = p_company_id
  returning vault_secret_id into v_secret_id;
  if v_secret_id is not null then
    delete from vault.secrets where id = v_secret_id;
  end if;

  perform app_private.reset_demo_company_without_ai_provider(p_company_id);
end
$$;

revoke execute on function app.get_company_gemini_configuration() from public;
revoke execute on function app.configure_company_gemini_credential(text, bytea, text, uuid)
  from public;
revoke execute on function app.remove_company_gemini_credential(uuid) from public;
revoke execute on function app.resolve_company_gemini_api_key() from public;
revoke execute on function app.cleanup_company_gemini_secret() from public;
revoke execute on function app_private.reset_demo_company(uuid)
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;
revoke execute on function app_private.reset_demo_company_without_ai_provider(uuid)
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;

grant execute on function app.get_company_gemini_configuration() to coordination_api;
grant execute on function app.configure_company_gemini_credential(text, bytea, text, uuid)
  to coordination_api;
grant execute on function app.remove_company_gemini_credential(uuid) to coordination_api;
grant execute on function app.resolve_company_gemini_api_key() to coordination_worker;

insert into app_private.migration_contract (version, name)
values ('20260926020000', 'company_gemini_byok');
