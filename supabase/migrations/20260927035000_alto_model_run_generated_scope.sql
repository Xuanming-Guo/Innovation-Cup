-- PostgreSQL computes stored generated columns after BEFORE triggers. Comparing
-- NEW.scope_id with OLD.scope_id in this trigger rejects otherwise legal model
-- checkpoints. Its company_id/demo_run_id inputs remain immutable and checked.
-- Preserve the deployed function's owner, ACL, attributes and all other bindings.
do $model_generated_scope$
declare
  definition text;
  mutable_columns text := 'array[''status'',''output_digest'',''usage'',''error_code'',''completed_at'']';
begin
  if not exists (
    select 1 from pg_attribute attribute
    join pg_attrdef generated on generated.adrelid = attribute.attrelid
      and generated.adnum = attribute.attnum
    where attribute.attrelid = 'app.model_runs'::regclass
      and attribute.attname = 'scope_id' and attribute.attgenerated = 's'
      and pg_get_expr(generated.adbin, generated.adrelid) = 'COALESCE(demo_run_id, company_id)'
  ) then
    raise exception using errcode = '55000', message = 'model_scope_generation_requires_review';
  end if;

  definition := replace(pg_get_functiondef('app.model_run_transition()'::regprocedure), chr(13), '');
  if length(definition) - length(replace(definition, mutable_columns, ''))
       <> 2 * length(mutable_columns)
     or position('old.status in (''succeeded'',''failed'',''cancelled'')' in definition) = 0
     or position('model_run_immutable_binding' in definition) = 0 then
    raise exception using errcode = '55000', message = 'model_transition_definition_requires_review';
  end if;

  definition := replace(definition, mutable_columns,
    'array[''status'',''output_digest'',''usage'',''error_code'',''completed_at'',''scope_id'']');
  execute definition;
end
$model_generated_scope$;

insert into app_private.migration_contract(version, name)
values ('20260927035000', 'alto_model_run_generated_scope');
