-- A successful ordinary planning lease renewal must not report the result of the
-- subsequent optional outbox UPDATE. Preserve the existing deployed definition,
-- including current token/owner/run/actor fences, ownership and execution grants.
do $renewal_result$
declare
  definition text;
  marker text;
begin
  definition := replace(pg_get_functiondef(
    'app.renew_durable_job_lease(uuid,uuid,uuid,uuid,integer)'::regprocedure
  ), chr(13), '');
  foreach marker in array array[
    '  v_until timestamptz;',
    '  if found then',
    '  return found;'
  ] loop
    if length(definition) - length(replace(definition, marker, '')) <> length(marker) then
      raise exception using errcode = '55000', message = 'lease_renewal_definition_requires_review';
    end if;
  end loop;
  if position('app.assert_alto_job_lease(p_company_id,p_job_id,p_lease_token)' in definition) = 0
     or position('exception when serialization_failure then return false; end;' in definition) = 0
  then
    raise exception using errcode = '55000', message = 'lease_renewal_fence_requires_review';
  end if;

  definition := replace(definition, '  v_until timestamptz;',
    E'  v_until timestamptz;\n  v_job_renewed boolean;');
  definition := replace(definition, '  if found then',
    E'  v_job_renewed := found;\n  if v_job_renewed then');
  definition := replace(definition, '  return found;', '  return v_job_renewed;');
  execute definition;
end
$renewal_result$;

insert into app_private.migration_contract(version, name)
values ('20260927034000', 'alto_job_lease_renewal_result');
