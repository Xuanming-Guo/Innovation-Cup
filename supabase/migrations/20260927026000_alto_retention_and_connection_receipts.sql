-- Narrow integration completion: optimistic connection receipts and physical transcript expiry.
drop function app.revoke_alto_connection(uuid,uuid,bigint);
create function app.revoke_alto_connection(p_company_id uuid,p_connection_id uuid,p_expected_version bigint) returns jsonb
language plpgsql security definer set search_path=pg_catalog,app as $$
declare c app.integration_connections%rowtype;
begin
 update app.integration_connections i set status='revoked',updated_at=clock_timestamp(),row_version=i.row_version+1
 where i.company_id=p_company_id and i.id=p_connection_id and i.row_version=p_expected_version
 and app.scope_access(i.company_id,i.demo_run_id,true) and exists(select 1 from app.company_memberships m
   where m.company_id=i.company_id and m.id=i.owner_membership_id and m.user_id=app.current_actor_id()) returning i.* into c;
 if not found then raise exception using errcode='40001',message='connection_version_or_authority_stale'; end if;
 update app.integration_grants set revoked_at=coalesce(revoked_at,clock_timestamp()) where company_id=p_company_id and connection_id=p_connection_id;
 return jsonb_build_object('id',c.id,'connection_id',c.id,'status',c.status,'version',c.row_version,'row_version',c.row_version);
end $$;
-- Revoked connections cannot continue to project calendars merely because a historical row exists.
create policy calendar_connection_current on app.calendar_event_versions as restrictive for select to coordination_api,coordination_worker
 using(exists(select 1 from app.integration_connections c where c.company_id=calendar_event_versions.company_id
   and c.id=connection_id and c.status in ('ready','degraded') and exists(select 1 from app.integration_grants g
     where g.company_id=c.company_id and g.connection_id=c.id and g.access_mode='read' and g.revoked_at is null)));
do $retention$ declare d text; begin
 d:=replace(pg_get_functiondef('app.fence_scope_write()'::regprocedure),chr(13),'');
 d:=replace(d,'  v_company := (v_row->>''company_id'')::uuid;',
 '  if tg_op=''DELETE'' and tg_table_name=''voice_transcriptions'' and v_runtime=''coordination_worker''
     and (v_row->>''expires_at'')::timestamptz<=clock_timestamp() then return old; end if;
  v_company := (v_row->>''company_id'')::uuid;');execute d;
 d:=replace(pg_get_functiondef('app.claim_expired_audio_cleanup(uuid,integer)'::regprocedure),chr(13),'');
 d:=replace(d,' for f in select pf.company_id,pf.id from app.private_files pf',
 ' delete from app.voice_transcriptions where expires_at<=clock_timestamp();
 for f in select pf.company_id,pf.id from app.private_files pf');execute d;
end $retention$;
revoke all on function app.revoke_alto_connection(uuid,uuid,bigint) from public;
grant execute on function app.revoke_alto_connection(uuid,uuid,bigint) to coordination_api;
insert into app_private.migration_contract(version,name) values ('20260927026000','alto_retention_and_connection_receipts');
