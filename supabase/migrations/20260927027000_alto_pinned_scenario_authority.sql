-- The live materializer may read only its leased run's immutable operator-authored manifest.
create function app.get_demo_scenario_manifest(p_company_id uuid,p_run_id uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog,app as $$
declare manifest jsonb;
begin
 if p_company_id is distinct from app.current_company_id() or p_run_id is null
   or p_run_id is distinct from app.current_demo_run_id() or not app.scope_access(p_company_id,p_run_id,true) then
   raise exception using errcode='42501',message='scenario_manifest_access_denied'; end if;
 perform app.assert_alto_job_lease(p_company_id,nullif(current_setting('app.job_id',true),'')::uuid,
   nullif(current_setting('app.lease_token',true),'')::uuid);
 select jsonb_build_object('manifest_payload',m.manifest_payload,'manifest_digest',encode(m.manifest_digest,'hex'),
   'scenario_key',m.scenario_key,'version',m.version) into manifest
 from app.demo_runs r join app.demo_scenario_manifests m on m.company_id=r.company_id
   and m.scenario_key=r.scenario_key and m.version=r.scenario_version
 where r.company_id=p_company_id and r.id=p_run_id and r.state='active';
 if manifest is null then raise exception using errcode='P0002',message='scenario_manifest_not_available'; end if;
 return manifest;
end $$;
create function app.get_demo_scenario_manifest() returns jsonb
language sql security definer set search_path=pg_catalog,app as $$
 select app.get_demo_scenario_manifest(app.current_company_id(),app.current_demo_run_id())
$$;
revoke all on function app.get_demo_scenario_manifest(uuid,uuid),app.get_demo_scenario_manifest()
 from public,anon,authenticated,service_role,coordination_api,coordination_worker;
grant execute on function app.get_demo_scenario_manifest(uuid,uuid),app.get_demo_scenario_manifest() to coordination_worker;
insert into app_private.migration_contract(version,name) values ('20260927027000','alto_pinned_scenario_authority');
