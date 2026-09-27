-- DB05: retain historical optimizer ledgers; ALTO promotes only unchanged checked candidates.
create table app.model_runs(
 id uuid primary key,company_id uuid not null,stage text not null check(stage in
 ('plan.propose','plan.revise','assistant.respond','preference.suggest','voice.transcribe','interpretation','brief','risk','explanation')),
 request_id uuid,parent_run_id uuid,provider_profile_version_id uuid,
 model text not null,prompt_version text not null,schema_version text not null,
 config_digest bytea not null check(octet_length(config_digest)=32),input_digest bytea not null check(octet_length(input_digest)=32),
 source_projection_digest bytea check(source_projection_digest is null or octet_length(source_projection_digest)=32),
 output_digest bytea check(output_digest is null or octet_length(output_digest)=32),
 status text not null check(status in ('queued','running','succeeded','failed','cancelled')),
 usage jsonb not null default '{}' check(jsonb_typeof(usage)='object'),error_code text,
 started_at timestamptz not null default clock_timestamp(),completed_at timestamptz,
 unique(company_id,id),foreign key(company_id,request_id) references app.planning_requests(company_id,id),
 foreign key(company_id,parent_run_id) references app.model_runs(company_id,id),
 check((status in ('succeeded','failed','cancelled'))=(completed_at is not null)),
 check(status<>'succeeded' or output_digest is not null)
);
create table app.ai_plan_proposals(
 id uuid primary key,company_id uuid not null,snapshot_id uuid not null,parent_proposal_id uuid,
 version integer not null check(version between 1 and 3),
 candidate_payload jsonb not null check(jsonb_typeof(candidate_payload)='object' and octet_length(candidate_payload::text)<=1048576),
 candidate_digest bytea not null check(octet_length(candidate_digest)=32),model_run_id uuid,
 author_kind text not null check(author_kind in ('ai_authored','authored_replay','authored_check')),
 created_at timestamptz not null default clock_timestamp(),unique(company_id,id),
 foreign key(company_id,snapshot_id) references app.planning_snapshots(company_id,id),
 foreign key(company_id,parent_proposal_id) references app.ai_plan_proposals(company_id,id),
 foreign key(company_id,model_run_id) references app.model_runs(company_id,id),
 check((version=1)=(parent_proposal_id is null)),check(author_kind<>'ai_authored' or model_run_id is not null)
);
create table app.plan_verification_runs(
 id uuid primary key,company_id uuid not null,proposal_id uuid not null,
 snapshot_digest bytea not null check(octet_length(snapshot_digest)=32),
 pre_candidate_digest bytea not null check(octet_length(pre_candidate_digest)=32),
 post_candidate_digest bytea not null check(octet_length(post_candidate_digest)=32),
 compiler_version text not null,z3_version text not null,
 product_status text not null check(product_status in ('CHECKED','VIOLATIONS_FOUND','UNABLE_TO_VERIFY','INVALID_CANDIDATE')),
 native_status text not null check(native_status in ('sat','unsat','unknown','invalid')),
 required_rule_ids text[] not null,covered_rule_ids text[] not null,unverified_rule_ids text[] not null,
 diagnostics jsonb not null default '{}' check(jsonb_typeof(diagnostics)='object'),
 duration_ms integer not null check(duration_ms>=0),timeout_ms integer not null check(timeout_ms>0),
 resource_limit bigint not null check(resource_limit>0),completed_at timestamptz not null default clock_timestamp(),
 unique(company_id,id),foreign key(company_id,proposal_id) references app.ai_plan_proposals(company_id,id),
 check(product_status<>'CHECKED' or (native_status='sat' and pre_candidate_digest=post_candidate_digest
   and cardinality(required_rule_ids)>0 and required_rule_ids<@covered_rule_ids and cardinality(unverified_rule_ids)=0))
);
create table app.plan_verification_rule_results(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,verification_run_id uuid not null,
 rule_key text not null,constraint_id uuid,source_version_id uuid,encoding_version text not null,
 fixed_values jsonb not null check(jsonb_typeof(fixed_values)='object'),
 result text not null check(result in ('pass','violation','unable','not_applicable')),
 safe_diagnostic text check(length(safe_diagnostic)<=2000),
 unique(company_id,id),unique(company_id,verification_run_id,rule_key),
 foreign key(company_id,verification_run_id) references app.plan_verification_runs(company_id,id),
 foreign key(company_id,constraint_id) references app.validated_constraints(company_id,id),
 foreign key(company_id,source_version_id) references app.source_versions(company_id,id),
 check(result<>'not_applicable' or length(btrim(safe_diagnostic))>0)
);
create table app.plan_validation_runs(
 id uuid primary key,company_id uuid not null,proposal_id uuid not null,
 candidate_digest bytea not null check(octet_length(candidate_digest)=32),passed boolean not null,
 issues jsonb not null check(jsonb_typeof(issues)='array'),validator_version text not null,
 completed_at timestamptz not null default clock_timestamp(),unique(company_id,id),
 foreign key(company_id,proposal_id) references app.ai_plan_proposals(company_id,id),
 check(not passed or jsonb_array_length(issues)=0)
);
create table app.work_item_versions(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,task_id uuid not null,version bigint not null check(version>0),
 source_plan_id uuid not null,approved_change_id uuid,previous_version_id uuid,
 content_digest bytea not null check(octet_length(content_digest)=32),payload jsonb not null check(jsonb_typeof(payload)='object'),
 created_at timestamptz not null default clock_timestamp(),unique(company_id,id),unique(company_id,task_id,version),
 foreign key(company_id,task_id) references app.work_items(company_id,task_id),
 foreign key(company_id,source_plan_id) references app.plans(company_id,id),
 foreign key(company_id,approved_change_id) references app.plan_changes(company_id,id),
 foreign key(company_id,previous_version_id) references app.work_item_versions(company_id,id)
);
do $scope$ declare t text; begin
 foreach t in array array['model_runs','ai_plan_proposals','plan_verification_runs','plan_verification_rule_results','plan_validation_runs','work_item_versions']
 loop perform app_private.install_alto_scope(('app.'||t)::regclass); end loop;
end $scope$;
alter table app.plans alter column solver_run_id drop not null,
 add column author_kind text not null default 'legacy_solver' check(author_kind in ('legacy_solver','ai_authored','authored_replay','authored_check')),
 add column ai_proposal_id uuid,add column verification_run_id uuid,add column validation_run_id uuid,add column parent_plan_id uuid,
 add foreign key(company_id,ai_proposal_id) references app.ai_plan_proposals(company_id,id),
 add foreign key(company_id,verification_run_id) references app.plan_verification_runs(company_id,id),
 add foreign key(company_id,validation_run_id) references app.plan_validation_runs(company_id,id),
 add foreign key(company_id,parent_plan_id) references app.plans(company_id,id),
 add constraint plan_author_ledger_shape check(
  (author_kind='legacy_solver' and solver_run_id is not null and ai_proposal_id is null and verification_run_id is null and validation_run_id is null)
  or (author_kind<>'legacy_solver' and solver_run_id is null and ai_proposal_id is not null and verification_run_id is not null and validation_run_id is not null));
alter table app.plans drop constraint plans_classification_check;
alter table app.plans add constraint plans_classification_check check(
 (author_kind='legacy_solver' and classification in ('OPTIMAL_WITHIN_MODEL','FEASIBLE'))
 or (author_kind<>'legacy_solver' and classification='VERIFIED_FIXED_CANDIDATE'));
select app_private.link_alto_scopes();

create function app.alto_immutable_row() returns trigger language plpgsql set search_path=pg_catalog as $$
begin raise exception using errcode='55000',message='immutable_ledger'; end $$;
create function app.model_run_transition() returns trigger language plpgsql set search_path=pg_catalog as $$
begin
 if old.status in ('succeeded','failed','cancelled') or (to_jsonb(new)-array['status','output_digest','usage','error_code','completed_at'])
    is distinct from (to_jsonb(old)-array['status','output_digest','usage','error_code','completed_at'])
 then raise exception using errcode='55000',message='model_run_immutable_binding'; end if;
 return new;
end $$;
create trigger model_run_transition before update on app.model_runs for each row execute function app.model_run_transition();
do $ledger$ declare t text; begin
 foreach t in array array['ai_plan_proposals','plan_verification_runs','plan_verification_rule_results','plan_validation_runs','work_item_versions'] loop
  execute format('create trigger alto_immutable before update or delete on app.%I for each row execute function app.alto_immutable_row()',t);
 end loop;
 foreach t in array array['model_runs','ai_plan_proposals','plan_verification_runs','plan_verification_rule_results','plan_validation_runs'] loop
  execute format('create policy alto_ledger_worker_insert on app.%I for insert to coordination_worker with check(app.can_manage_planning(company_id,app.current_actor_id()))',t);
  execute format('create policy alto_ledger_manager_read on app.%I for select to coordination_api,coordination_worker using(app.can_manage_planning(company_id,app.current_actor_id()))',t);
  execute format('grant select on app.%I to coordination_api,coordination_worker',t);
  execute format('grant insert on app.%I to coordination_worker',t);
 end loop;
end $ledger$;
create policy model_run_worker_update on app.model_runs for update to coordination_worker
 using(app.can_manage_planning(company_id,app.current_actor_id())) with check(app.can_manage_planning(company_id,app.current_actor_id()));
grant update(status,output_digest,usage,error_code,completed_at) on app.model_runs to coordination_worker;
create policy work_version_read on app.work_item_versions for select to coordination_api,coordination_worker
 using(app.can_read_task(app.current_actor_id(),company_id,task_id));
grant select on app.work_item_versions to coordination_api,coordination_worker;

create function app.promote_verified_ai_proposal(p_company_id uuid,p_proposal_id uuid,p_verification_id uuid,p_validation_id uuid)
returns uuid language plpgsql security definer set search_path=pg_catalog,app as $$
declare p app.ai_plan_proposals%rowtype; v app.plan_verification_runs%rowtype; x app.plan_validation_runs%rowtype;
 s app.planning_snapshots%rowtype; existing_id uuid; required_keys text[];
begin
 select * into p from app.ai_plan_proposals where company_id=p_company_id and id=p_proposal_id;
 if not found or not app.scope_access(p_company_id,p.demo_run_id,true)
   or not app.can_manage_planning(p_company_id,app.current_actor_id()) then
   raise exception using errcode='42501',message='proposal_access_denied'; end if;
 perform pg_advisory_xact_lock(hashtextextended(p.id::text,0));
 select id into existing_id from app.plans where company_id=p_company_id and ai_proposal_id=p.id;
 if found then return existing_id; end if;
 select * into strict s from app.planning_snapshots where company_id=p_company_id and id=p.snapshot_id and scope_id=p.scope_id;
 select * into v from app.plan_verification_runs where company_id=p_company_id and id=p_verification_id
   and proposal_id=p.id and scope_id=p.scope_id;
 select * into x from app.plan_validation_runs where company_id=p_company_id and id=p_validation_id
   and proposal_id=p.id and scope_id=p.scope_id;
 select coalesce(array_agg(c.constraint_key),'{}') into required_keys from app.planning_snapshot_constraints sc
   join app.validated_constraints c on c.company_id=sc.company_id and c.id=sc.constraint_id
   where sc.company_id=p_company_id and sc.snapshot_id=s.id and c.strength='hard';
 if v.id is null or x.id is null or v.product_status<>'CHECKED' or v.native_status<>'sat'
   or not x.passed or jsonb_array_length(x.issues)<>0
   or v.snapshot_digest<>s.snapshot_digest or v.pre_candidate_digest<>p.candidate_digest
   or v.post_candidate_digest<>p.candidate_digest or x.candidate_digest<>p.candidate_digest
   or not (required_keys<@v.required_rule_ids) or not (v.required_rule_ids<@v.covered_rule_ids)
   or cardinality(v.unverified_rule_ids)<>0 or cardinality(required_keys)=0 then
   raise exception using errcode='23514',message='candidate_verification_incomplete'; end if;
 if p.version>1 and not exists(select 1 from app.ai_plan_proposals parent
   where parent.company_id=p_company_id and parent.id=p.parent_proposal_id and parent.scope_id=p.scope_id
     and parent.snapshot_id=p.snapshot_id and parent.version=p.version-1) then
   raise exception using errcode='23514',message='proposal_lineage_invalid'; end if;
 insert into app.plans(id,company_id,demo_run_id,request_id,snapshot_id,solver_run_id,state,classification,proposal_digest,
   author_kind,ai_proposal_id,verification_run_id,validation_run_id,parent_plan_id)
 values(p.id,p_company_id,p.demo_run_id,s.request_id,s.id,null,'proposed','VERIFIED_FIXED_CANDIDATE',p.candidate_digest,
   p.author_kind,p.id,v.id,x.id,(select id from app.plans where company_id=p_company_id and ai_proposal_id=p.parent_proposal_id));
 insert into app.plan_task_placements(company_id,demo_run_id,plan_id,task_id,start_slot,end_slot,owner_resource_id)
 select p_company_id,p.demo_run_id,p.id,r.task_id,r.start_slot,r.end_slot,r.owner_resource_id
   from jsonb_to_recordset(p.candidate_payload->'placements') r(task_id uuid,start_slot integer,end_slot integer,owner_resource_id uuid);
 insert into app.plan_schedule_blocks(company_id,demo_run_id,plan_id,task_id,resource_id,start_slot,end_slot,capacity_units,block_role)
 select p_company_id,p.demo_run_id,p.id,r.task_id,r.resource_id,r.start_slot,r.end_slot,r.capacity_units,r.role
   from jsonb_to_recordset(p.candidate_payload->'blocks') r(task_id uuid,resource_id uuid,start_slot integer,end_slot integer,capacity_units integer,role text);
 if not exists(select 1 from app.plan_task_placements where company_id=p_company_id and plan_id=p.id) then
   raise exception using errcode='23514',message='candidate_has_no_tasks'; end if;
 insert into app.plan_approval_requirements(company_id,demo_run_id,plan_id,approval_domain,requirement_kind,authority_kind,
   artifact_digest,proposal_digest,snapshot_digest,source_manifest_digest,base_company_revision,policy_revision,policy_version,reason)
 select p_company_id,p.demo_run_id,p.id,'planning','plan_commit','company_manager',p.candidate_digest,p.candidate_digest,
   s.snapshot_digest,s.source_manifest_digest,s.base_company_revision,c.policy_revision,
   s.policy->>'policy_version','Approve the exact fixed candidate and its current source/policy bindings.'
   from app.companies c where c.id=p_company_id;
 return p.id;
end $$;
revoke all on function app.alto_immutable_row(),app.model_run_transition(),app.promote_verified_ai_proposal(uuid,uuid,uuid,uuid) from public;
grant execute on function app.promote_verified_ai_proposal(uuid,uuid,uuid,uuid) to coordination_worker;
insert into app_private.migration_contract(version,name) values ('20260927013000','alto_ai_proposals_fixed_verification');
