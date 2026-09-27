-- DB05 Vault: visitor-owned immutable versions, with explicit immutable live-run binding.
create table app.demo_provider_profiles(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,owner_membership_id uuid not null,
 status text not null default 'active' check(status in ('active','revoked')),
 created_at timestamptz not null default clock_timestamp(),unique(company_id,id),unique(company_id,owner_membership_id),
 foreign key(company_id,owner_membership_id) references app.company_memberships(company_id,id)
);
create table app.demo_provider_profile_versions(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,profile_id uuid not null,
 version integer not null check(version>0),provider text not null check(provider in ('gemini_developer_api','vertex_ai')),
 credential_kind text not null check(credential_kind in ('api_key','vertex_service_account')),
 vault_secret_id uuid not null unique,credential_fingerprint bytea not null check(octet_length(credential_fingerprint)=32),
 credential_hint text not null check(credential_hint ~ '^[0-9a-f]{12}$'),validated_model text not null,
 vertex_project_id text,vertex_client_email text,vertex_location text,
 validation_status text not null default 'validated' check(validation_status='validated'),
 created_at timestamptz not null default clock_timestamp(),revoked_at timestamptz,
 unique(company_id,id),unique(company_id,profile_id,version),
 foreign key(company_id,profile_id) references app.demo_provider_profiles(company_id,id),
 check((provider='gemini_developer_api' and credential_kind='api_key' and vertex_project_id is null and vertex_client_email is null and vertex_location is null)
   or(provider='vertex_ai' and credential_kind='vertex_service_account' and vertex_project_id is not null and vertex_client_email is not null and vertex_location is not null))
);
create table app.demo_run_provider_bindings(
 company_id uuid not null,run_id uuid not null,profile_version_id uuid not null,bound_by uuid not null,
 bound_at timestamptz not null default clock_timestamp(),primary key(company_id,run_id),
 foreign key(company_id,run_id) references app.demo_runs(company_id,id),
 foreign key(company_id,profile_version_id) references app.demo_provider_profile_versions(company_id,id),
 foreign key(company_id,bound_by) references app.company_memberships(company_id,id)
);
alter table app.model_runs add foreign key(company_id,provider_profile_version_id) references app.demo_provider_profile_versions(company_id,id);
alter table app.demo_provider_profiles enable row level security;
alter table app.demo_provider_profile_versions enable row level security;
alter table app.demo_run_provider_bindings enable row level security;
revoke all on app.demo_provider_profiles,app.demo_provider_profile_versions,app.demo_run_provider_bindings
 from public,anon,authenticated,service_role,coordination_api,coordination_worker;

create function app.configure_demo_ai_credential(p_provider text,p_credential_kind text,p_credential_secret text,
 p_credential_fingerprint bytea,p_validated_model text,p_vertex_project_id text,p_vertex_client_email text,
 p_vertex_location text,p_correlation_id uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog,app,vault as $$
declare member_id uuid; v_profile_id uuid; version_id uuid; version_number integer; secret_id uuid; secret_json jsonb;
begin
 if not app.request_context_present() or not app.can_manage_planning(app.current_company_id(),app.current_actor_id())
   or not exists(select 1 from app.demo_workspace_policies where company_id=app.current_company_id() and enabled) then
   raise exception using errcode='42501',message='demo_provider_owner_required'; end if;
 if p_credential_secret is null or length(p_credential_secret) not between 20 and 65536
   or p_credential_fingerprint is null or octet_length(p_credential_fingerprint)<>32
   or p_validated_model is null or length(btrim(p_validated_model)) not between 1 and 200 or p_correlation_id is null then
   raise exception using errcode='22023',message='invalid_ai_provider_configuration'; end if;
 if p_provider='vertex_ai' and p_credential_kind='vertex_service_account' then
   begin secret_json:=p_credential_secret::jsonb; exception when others then
     raise exception using errcode='22023',message='invalid_ai_provider_configuration'; end;
   if secret_json->>'type' is distinct from 'service_account'
     or secret_json->>'project_id' is distinct from p_vertex_project_id
     or secret_json->>'client_email' is distinct from p_vertex_client_email
     or p_vertex_project_id is null or p_vertex_project_id !~ '^[a-z][a-z0-9-]{4,28}[a-z0-9]$'
     or p_vertex_client_email is null or split_part(p_vertex_client_email,'@',2)<>p_vertex_project_id||'.iam.gserviceaccount.com'
     or p_vertex_location is null or p_vertex_location !~ '^(global|[a-z]+-[a-z]+[0-9])$' then
     raise exception using errcode='22023',message='invalid_ai_provider_configuration'; end if;
 elsif not(p_provider='gemini_developer_api' and p_credential_kind='api_key' and p_vertex_project_id is null
    and p_vertex_client_email is null and p_vertex_location is null) then
   raise exception using errcode='22023',message='invalid_ai_provider_configuration'; end if;
 select id into strict member_id from app.company_memberships where company_id=app.current_company_id()
   and user_id=app.current_actor_id() and membership_status='active';
 perform pg_advisory_xact_lock(hashtextextended(member_id::text,0));
 insert into app.demo_provider_profiles(company_id,owner_membership_id) values(app.current_company_id(),member_id)
   on conflict(company_id,owner_membership_id) do update set status='active' returning id into v_profile_id;
 select coalesce(max(v.version),0)+1 into version_number from app.demo_provider_profile_versions v
   where v.company_id=app.current_company_id() and v.profile_id=v_profile_id;
 version_id:=gen_random_uuid();
 secret_id:=vault.create_secret(p_credential_secret,'alto-demo-'||version_id::text,'ALTO private visitor-owned provider version');
 insert into app.demo_provider_profile_versions(id,company_id,profile_id,version,provider,credential_kind,vault_secret_id,
   credential_fingerprint,credential_hint,validated_model,vertex_project_id,vertex_client_email,vertex_location)
 values(version_id,app.current_company_id(),v_profile_id,version_number,p_provider,p_credential_kind,secret_id,
   p_credential_fingerprint,encode(substring(p_credential_fingerprint from 1 for 6),'hex'),p_validated_model,
   p_vertex_project_id,p_vertex_client_email,p_vertex_location);
 return jsonb_build_object('profile_id',v_profile_id,'profile_version_id',version_id,'version',version_number,
   'status','configured','provider',p_provider,'credential_kind',p_credential_kind,
   'credential_hint',encode(substring(p_credential_fingerprint from 1 for 6),'hex'),'validated_model',p_validated_model);
end $$;
create function app.get_demo_ai_configuration() returns table(provider text,credential_kind text,status text,credential_hint text,
 validated_model text,vertex_project_id text,vertex_client_email text,vertex_location text,
 configured_at timestamptz,validated_at timestamptz,rotated_at timestamptz)
language plpgsql stable security definer set search_path=pg_catalog,app as $$
begin
 if not app.request_context_present() or not app.has_active_membership(app.current_company_id(),app.current_actor_id()) then
   raise exception using errcode='42501',message='demo_provider_owner_required'; end if;
 return query select v.provider,v.credential_kind,case when v.revoked_at is null then 'configured' else 'not_configured' end,
   v.credential_hint,v.validated_model,v.vertex_project_id,v.vertex_client_email,v.vertex_location,
   v.created_at,v.created_at,case when v.version>1 then v.created_at end
 from app.demo_provider_profiles p join app.company_memberships m on m.company_id=p.company_id and m.id=p.owner_membership_id
 join app.demo_provider_profile_versions v on v.company_id=p.company_id and v.profile_id=p.id
 where p.company_id=app.current_company_id() and m.user_id=app.current_actor_id() and m.membership_status='active'
   and p.status='active' and v.revoked_at is null order by v.version desc limit 1;
 if not found then return query select 'gemini_developer_api'::text,'api_key'::text,'not_configured'::text,
   null::text,null::text,null::text,null::text,null::text,null::timestamptz,null::timestamptz,null::timestamptz; end if;
end $$;
create function app.bind_demo_provider(p_company_id uuid,p_run_id uuid,p_version_id uuid) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
declare member_id uuid; existing_version uuid;
begin
 select m.id into member_id from app.company_memberships m join app.demo_runs r
   on r.company_id=m.company_id and r.owner_membership_id=m.id
 where r.company_id=p_company_id and r.id=p_run_id and r.mode='live' and r.state='active'
   and m.user_id=app.current_actor_id() and m.membership_status='active' and p_company_id=app.current_company_id();
 if member_id is null or not exists(select 1 from app.demo_provider_profile_versions v join app.demo_provider_profiles p
   on p.company_id=v.company_id and p.id=v.profile_id where v.company_id=p_company_id and v.id=p_version_id
     and p.owner_membership_id=member_id and p.status='active' and v.revoked_at is null) then
   raise exception using errcode='42501',message='demo_provider_binding_denied'; end if;
 select profile_version_id into existing_version from app.demo_run_provider_bindings where company_id=p_company_id and run_id=p_run_id;
 if found and existing_version<>p_version_id then raise exception using errcode='55000',message='run_provider_binding_immutable'; end if;
 insert into app.demo_run_provider_bindings(company_id,run_id,profile_version_id,bound_by)
   values(p_company_id,p_run_id,p_version_id,member_id) on conflict(company_id,run_id) do nothing;
end $$;
create function app.revoke_demo_provider_version(p_company_id uuid,p_version_id uuid) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 update app.demo_provider_profile_versions v set revoked_at=coalesce(v.revoked_at,clock_timestamp())
 from app.demo_provider_profiles p join app.company_memberships m on m.company_id=p.company_id and m.id=p.owner_membership_id
 where v.company_id=p.company_id and v.profile_id=p.id and v.company_id=p_company_id and v.id=p_version_id
   and p_company_id=app.current_company_id() and m.user_id=app.current_actor_id() and m.membership_status='active';
 if not found then raise exception using errcode='42501',message='demo_provider_owner_required'; end if;
end $$;
alter function app.resolve_company_ai_credential() rename to resolve_ordinary_company_ai_credential;
revoke all on function app.resolve_ordinary_company_ai_credential() from public,anon,authenticated,service_role,coordination_api,coordination_worker;
create function app.resolve_company_ai_credential() returns table(provider text,credential_kind text,credential_secret text,
 validated_model text,vertex_project_id text,vertex_client_email text,vertex_location text)
language plpgsql security definer set search_path=pg_catalog,app,vault as $$
begin
 if app.current_demo_run_id() is null then return query select * from app.resolve_ordinary_company_ai_credential(); return; end if;
 perform app.assert_alto_job_lease(app.current_company_id(),nullif(current_setting('app.job_id',true),'')::uuid,
   nullif(current_setting('app.lease_token',true),'')::uuid);
 return query select v.provider,v.credential_kind,s.decrypted_secret,v.validated_model,v.vertex_project_id,v.vertex_client_email,v.vertex_location
 from app.demo_run_provider_bindings b join app.demo_runs r on r.company_id=b.company_id and r.id=b.run_id
 join app.demo_provider_profile_versions v on v.company_id=b.company_id and v.id=b.profile_version_id
 join app.demo_provider_profiles p on p.company_id=v.company_id and p.id=v.profile_id
 join vault.decrypted_secrets s on s.id=v.vault_secret_id
 where b.company_id=app.current_company_id() and b.run_id=app.current_demo_run_id()
   and r.state='active' and r.mode='live' and v.revoked_at is null and p.status='active'
   and p.owner_membership_id=r.owner_membership_id and app.scope_access(r.company_id,r.id,true);
 if not found then raise exception using errcode='P0002',message='demo_provider_not_bound'; end if;
end $$;
revoke all on function app.configure_demo_ai_credential(text,text,text,bytea,text,text,text,text,uuid),app.get_demo_ai_configuration(),
 app.bind_demo_provider(uuid,uuid,uuid),app.revoke_demo_provider_version(uuid,uuid),app.resolve_company_ai_credential() from public;
grant execute on function app.configure_demo_ai_credential(text,text,text,bytea,text,text,text,text,uuid),app.get_demo_ai_configuration(),
 app.bind_demo_provider(uuid,uuid,uuid),app.revoke_demo_provider_version(uuid,uuid) to coordination_api;
grant execute on function app.resolve_company_ai_credential() to coordination_worker;
insert into app_private.migration_contract(version,name) values ('20260927016000','alto_demo_provider_vault');
