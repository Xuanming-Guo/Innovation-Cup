'use strict';
const $=id=>document.getElementById(id);
let data=null,caseIndex=0,position=0,playing=false,page=0,frame=null,employeePage=0,taskPage=0,inspectorMode='directory';
const escText=(node,value)=>{node.textContent=value;};
const make=(tag,text='',className='')=>{const node=document.createElement(tag);node.textContent=text;if(className)node.className=className;return node;};
function current(){return data.cases[caseIndex];}
function caseEvents(){return data.events.filter(e=>e.scenario_id===current().id);}
function stop(){playing=false;if(frame!==null)cancelAnimationFrame(frame);frame=null;}
function setStatus(message){$('status').textContent=message;}
function selectCase(index){stop();caseIndex=Math.min(index,data.cases.length-1);position=0;page=0;render();}
function slotText(slot){
 const info=data.company_inspector?.company;if(!info||slot===null||slot===undefined)return String(slot??'NOT_AVAILABLE');
 const at=new Date(new Date(info.anchor).getTime()+Number(slot)*info.slot_minutes*60000);
 return new Intl.DateTimeFormat('en',{timeZone:info.timezone,weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).format(at)+` (slot ${slot})`;
}
function fact(label,value){const item=make('div','','fact');item.append(make('strong',String(value)),make('span',label));return item;}
function detailRow(label,value){const row=make('p','','profile-detail');row.append(make('strong',label+': '),document.createTextNode?document.createTextNode(String(value)):make('span',String(value)));return row;}
function profileCard(title,subtitle,rows,status=''){
 const article=make('article','','profile-card '+status),heading=make('h3',title),small=make('small',subtitle);article.append(heading,small);
 for(const [label,value] of rows)article.append(detailRow(label,value));return article;
}
function renderCompanyFacts(){
 const inspector=data.company_inspector;if(!inspector)return;
 $('explorer-notice').textContent=inspector.label+' · '+inspector.notice;
 $('company-facts').replaceChildren(
   fact('fictional employees',inspector.counts.employees.toLocaleString()),fact('teams',inspector.counts.teams),
   fact('projects',inspector.counts.projects),fact('tasks',inspector.counts.tasks.toLocaleString()),
   fact('workspace sources',inspector.counts.sources),fact('explicit grants',inspector.counts.grants.toLocaleString()));
 if(!$('employee-team').children.length||$('employee-team').children.length===1){
   for(const team of inspector.teams){const option=make('option',team.name);option.value=team.team_id;$('employee-team').append(option);}
 }
}
function renderEmployees(){
 const inspector=data.company_inspector;if(!inspector)return;
 const query=$('employee-search').value.trim().toLowerCase(),team=$('employee-team').value,role=$('employee-role').value;
 const rows=inspector.employees.filter(person=>{
   const haystack=[person.employee_id,person.name,person.role,...person.confirmed_skills,...person.declared_skills,...person.teams.map(item=>item.name)].join(' ').toLowerCase();
   return (!query||haystack.includes(query))&&(!team||person.teams.some(item=>item.team_id===team))&&(!role||person.role===role);
 });
 const size=12,maxPage=Math.max(0,Math.ceil(rows.length/size)-1);employeePage=Math.min(employeePage,maxPage);
 $('employee-directory').replaceChildren();
 for(const person of rows.slice(employeePage*size,employeePage*size+size)){
   const skills=person.confirmed_skills.join(', ')||'none';
   $('employee-directory').append(profileCard(person.name,`${person.employee_id} · ${person.role}`,[
     ['Teams',person.teams.map(item=>item.name).join(', ')],['Manager',person.manager_name],['Confirmed skills',skills],
     ['Declared skills',person.declared_skills.join(', ')||'none'],['Qualifications',person.qualifications.join(', ')||'none'],
     ['Capacity',`${person.daily_budget_minutes} min/day · ${person.weekly_budget_minutes} min/week`],
     ['Current schedule',`${person.scheduled_task_count} tasks · ${person.scheduled_minutes} min`],
     ['Evidence',`${person.source_ref} · profile ${person.profile_versions.profile}`]
   ],person.role));
 }
 $('employee-count').textContent=`${rows.length.toLocaleString()} of ${inspector.employees.length.toLocaleString()} fictional profiles match.`;
 $('employee-page').textContent=`page ${employeePage+1} / ${maxPage+1}`;$('employee-prev').disabled=employeePage===0;$('employee-next').disabled=employeePage>=maxPage;
}
function renderCompanyStructure(){
 const inspector=data.company_inspector;if(!inspector)return;
 $('team-directory').replaceChildren();
 for(const team of inspector.teams)$('team-directory').append(profileCard(team.name,`${team.team_id} · ${team.function}`,[
   ['Manager',team.manager_name],['People',team.employee_count],['Projects',team.project_count],['Tasks',team.task_count]]));
 $('project-directory').replaceChildren();
 for(const project of inspector.projects)$('project-directory').append(profileCard(project.title,`${project.project_id} · ${project.classification}`,[
   ['Purpose',project.purpose],['Team',project.team_name],['Manager',project.manager_name],['Tasks',project.task_count],['Agreed deadline',slotText(project.agreed_deadline_slot)],['Evidence',project.source_ref]]));
}
function renderTasks(){
 const inspector=data.company_inspector;if(!inspector)return;
 const query=$('task-search').value.trim().toLowerCase();
 const rows=inspector.tasks.filter(task=>!query||[task.task_id,task.title,task.project_id,task.project_title,...task.required_skills,...task.eligible_owners.flatMap(owner=>[owner.employee_id,owner.name])].join(' ').toLowerCase().includes(query));
 const size=20,maxPage=Math.max(0,Math.ceil(rows.length/size)-1);taskPage=Math.min(taskPage,maxPage);$('task-directory').replaceChildren();
 for(const task of rows.slice(taskPage*size,taskPage*size+size))$('task-directory').append(profileCard(task.title,`${task.task_id} · ${task.project_title}`,[
   ['Lifecycle / priority',`${task.lifecycle} / ${task.priority}`],['Effort',task.effort_minutes+' min'],['Agreed deadline',slotText(task.agreed_deadline_slot)],
   ['Eligible owners',task.eligible_owners.map(owner=>owner.name).join(', ')],['Dependencies',task.dependencies.join(', ')||'none'],
   ['Movement',`${task.movable?'movable':'fixed'} · owner change ${task.allow_owner_change?'allowed':'not allowed'}`],['Evidence',task.source_refs.join(', ')]
 ]));
 $('task-count').textContent=`${rows.length.toLocaleString()} of ${inspector.tasks.length.toLocaleString()} task records match.`;
 $('task-page').textContent=`page ${taskPage+1} / ${maxPage+1}`;$('task-prev').disabled=taskPage===0;$('task-next').disabled=taskPage>=maxPage;
}
function selectedGraph(){
 const methods=current().methods,requested=$('graph-method').value;
 if(methods[requested]?.graph)return methods[requested].graph;
 const fallback=Object.values(methods).find(method=>method.graph);return fallback?.graph??null;
}
function graphSubset(graph){
 if($('graph-scope').value==='considered')return {nodes:graph.nodes,edges:graph.edges};
 const seed=new Set(graph.nodes.filter(node=>(node.flags??[node.status]).includes('direct')||(node.flags??[node.status]).includes('changed')).map(node=>node.id));
 const keep=new Set(seed);
 for(const edge of graph.edges)if(seed.has(edge.source)||seed.has(edge.target)){keep.add(edge.source);keep.add(edge.target);}
 return {nodes:graph.nodes.filter(node=>keep.has(node.id)),edges:graph.edges.filter(edge=>keep.has(edge.source)&&keep.has(edge.target))};
}
function renderGraph(){
 const graph=selectedGraph();$('graph-canvas').replaceChildren();$('graph-records').replaceChildren();$('graph-stats').replaceChildren();
 if(!graph){$('graph-notice').textContent='NOT_AVAILABLE — this method has no concrete schedule graph for the selected case.';return;}
 $('graph-notice').textContent=graph.label+' · '+graph.notice;
 $('graph-stats').replaceChildren(fact('company tasks',graph.stats.company_tasks),fact('tasks considered',graph.stats.considered_tasks),fact('directly requested / inserted',graph.stats.direct_tasks),fact('schedule changes',graph.stats.changed_tasks),fact('employees in rendered graph',graph.stats.rendered_employees));
 const subset=graphSubset(graph),nodeById=new Map(subset.nodes.map(node=>[node.id,node]));
 for(const node of subset.nodes){const flags=(node.flags??[node.status]).join(' '),button=make('button',`${node.kind}: ${node.label} — ${node.subtitle}`,`graph-record ${flags}`);button.onclick=()=>{$('graph-node-detail').textContent=JSON.stringify(node,null,2);};$('graph-records').append(button);}
 if(!document.createElementNS){$('graph-canvas').append(make('p','Graph drawing requires a browser; the accessible records remain available.','muted'));return;}
 const order=['source','project','task','employee','team'],groups=new Map(order.map(kind=>[kind,subset.nodes.filter(node=>node.kind===kind)]));
 const maxRows=Math.max(1,...[...groups.values()].map(items=>items.length)),width=1180,height=Math.max(430,maxRows*66+60),positions=new Map();
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',`${graph.scenario_id} ${graph.method} coordination impact graph`);
 order.forEach((kind,column)=>{const items=groups.get(kind),x=25+column*230;items.forEach((node,row)=>positions.set(node.id,{x,y:45+row*66}));});
 for(const edge of subset.edges){const a=positions.get(edge.source),b=positions.get(edge.target);if(!a||!b)continue;const line=document.createElementNS(svg.namespaceURI,'line');for(const [key,value] of Object.entries({x1:a.x+172,y1:a.y+20,x2:b.x,y2:b.y+20,class:`graph-edge ${edge.kind} ${edge.status}`}))line.setAttribute(key,value);const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=edge.kind;line.append(title);svg.append(line);}
 for(const node of subset.nodes){const position=positions.get(node.id),group=document.createElementNS(svg.namespaceURI,'g');group.setAttribute('class',`graph-node ${node.kind} ${(node.flags??[node.status]).join(' ')}`);group.setAttribute('role','button');group.setAttribute('tabindex','0');group.setAttribute('transform',`translate(${position.x} ${position.y})`);
   const rect=document.createElementNS(svg.namespaceURI,'rect');rect.setAttribute('width','172');rect.setAttribute('height','42');rect.setAttribute('rx','6');const label=document.createElementNS(svg.namespaceURI,'text');label.setAttribute('x','9');label.setAttribute('y','17');label.textContent=node.label.length>24?node.label.slice(0,23)+'…':node.label;const sub=document.createElementNS(svg.namespaceURI,'text');sub.setAttribute('x','9');sub.setAttribute('y','33');sub.setAttribute('class','subtitle');sub.textContent=node.subtitle.length>28?node.subtitle.slice(0,27)+'…':node.subtitle;group.append(rect,label,sub);group.onclick=()=>{$('graph-node-detail').textContent=JSON.stringify(node,null,2);};group.onkeydown=event=>{if(event.key==='Enter'||event.key===' ')group.onclick();};svg.append(group);}
 $('graph-canvas').append(svg);
}
function renderProjectionGraph(projection){
 $('pov-graph').replaceChildren();if(!projection)return;
 const owners=new Map((projection.panels.before??[]).map(block=>[block.task_id,block.employee_id]));
 for(const task of projection.panels.today??[]){const row=make('div','','projection-relation');row.append(make('span',task.title,'relation-task'),make('span','→'),make('span',owners.get(task.task_id)??'owner hidden','relation-person'));
   if(task.dependencies?.length)row.append(make('small','after '+task.dependencies.join(', ')));$('pov-graph').append(row);}
}
function renderInspector(){renderCompanyFacts();renderEmployees();renderCompanyStructure();renderTasks();if(inspectorMode==='graph')renderGraph();}
function displayValue(o){
 if(!o)return 'NOT_AVAILABLE';
 if(o.status!=='MEASURED')return o.status;
 const v=o.value;
 if(typeof v!=='object')return String(v);
 switch(o.metric_id){
 case 'changed_commitments':return `${v.tasks} tasks · ${v.blocks} blocks`;
 case 'owner_churn':return `${v.count} owners · ${v.started} started`;
 case 'displacement':return `${v.total.toLocaleString()} total · ${v.median} median · ${v.maximum} max min`;
 case 'preservation':return `${v.unchanged} / ${v.considered} · ${v.rate===null?'no denominator':(v.rate*100).toFixed(1)+'%'}`;
 case 'replans':return `${v.planning_attempts} attempts · ${v.cascade_cycles} cascades`;
 case 'contacts':return `${v.count} people`;
 case 'clarifications_approvals':return `${v.required_clarifications} questions · ${v.approval_decisions} decisions`;
 case 'invalid_delegations':return `${v.invalid} / ${v.assignments}`;
 case 'capacity_overload':return `${v.active_minutes} min · ${v.overlap_pairs} overlaps`;
 case 'dependency_deadlines':return `${v.precedence} precedence · ${v.missed_agreed} missed · ${v.agreed_lateness_minutes} late min`;
 case 'priority_service':return `${v.incident_resolution} resolution · ${v.blocking_tasks} blocking min`;
 case 'collateral':return `${v.moved} moved · ${v.deadlines_changed} deadlines`;
 case 'completion':return `Hikari ${v.hikari??'unavailable'} · incident ${v.incident??'unavailable'} min`;
 case 'hard_violations':case 'source_authority':return `${v.count} violations`;
 case 'scope':return `${v.considered.tasks} considered / ${v.full.tasks} · ${v.replanned.tasks} replanned`;
 case 'planning_latency':return Object.entries(v.stage_ms).map(([k,n])=>`${k.replaceAll('_',' ')} ${n.toFixed(2)} ms`).join(' · ');
 default:return JSON.stringify(v);
 }
}
function metricDetail(id){
 const definition=data.registry.metrics.find(m=>m.metric_id===id);
 const observations=['naive','product_replay'].map(m=>current().methods[m]?.metrics.find(o=>o.metric_id===id)).filter(Boolean);
 observations.push(current().product.find(o=>o.metric_id===id));
 $('metric-explanation').replaceChildren();
 const p=document.createElement('p');p.textContent=definition.definition;$('metric-explanation').append(p);
 for(const o of observations){for(const ref of o.source_event_or_artifact_refs){const a=document.createElement('a');a.href=window.BENCHMARK_DATA?ref:'/api/artifact?path='+encodeURIComponent(ref);a.target='_blank';a.rel='noreferrer';a.textContent=`${o.approach_or_condition}: ${ref} ↗`;a.style.display='block';$('metric-explanation').append(a);}}
 $('metric-json').textContent=JSON.stringify(observations,null,2);$('metric-detail').open=true;
}
function renderMetrics(){
 $('metrics').replaceChildren();
 for(const def of data.registry.metrics.filter(m=>m.primary)){
 const tr=document.createElement('tr'),name=document.createElement('td'),button=document.createElement('button');button.textContent=def.name;button.onclick=()=>metricDetail(def.metric_id);name.append(button);tr.append(name);
 const observations=['naive','product_replay'].map(method=>current().methods[method]?.metrics.find(o=>o.metric_id===def.metric_id));observations.push(current().product.find(o=>o.metric_id===def.metric_id));
 for(const o of observations){const td=document.createElement('td');td.textContent=displayValue(o);if(o?.status!=='MEASURED')td.className='missing';const label=document.createElement('small');label.textContent=o?.evidence_class??'recording unavailable';td.append(label);td.title=o?.missing_or_invalid_reason??def.definition;tr.append(td);}
 $('metrics').append(tr);
 }
}
function renderProjection(){
 const viewer=$('viewer').value,isJudge=viewer==='judge';
 for(const id of ['scorecard','trace-section','story','playback'])$(id).hidden=!isJudge;
 $('pov').hidden=isJudge;
 if(isJudge)return;
 const projection=current().methods.product_replay?.projections.find(p=>p.viewer_id===viewer);
 $('cards').replaceChildren();$('pov-states').replaceChildren();
 if(!projection){$('pov-notice').textContent='NOT_AVAILABLE — no captured replay for this persona and case.';$('pov-raw').textContent='';renderProjectionGraph(null);return;}
 $('pov-notice').textContent=projection.label+' · '+projection.panels.notice;
 for(const [key,value] of Object.entries(projection.states)){const s=document.createElement('span');s.className='state';s.textContent=key.replaceAll('_',' ')+': '+value;$('pov-states').append(s);}
 for(const card of projection.panels.today??[]){const article=document.createElement('article');article.className='card';const h=document.createElement('h3');h.textContent=card.title;article.append(h);
 for(const text of [card.brief,card.purpose]){const p=document.createElement('p');p.textContent=text;article.append(p);}
 const segments=(card.suggested_segments??[]).map(span=>`${slotText(span.start)}–${slotText(span.end)}`).join('; ');
 const dl=document.createElement('dl');for(const [label,value] of [['Deliverable',card.deliverable],['Acceptance',card.acceptance_criteria.join('; ')],['Active effort',card.effort_minutes+' minutes'],['Work window',`${slotText(card.window.start)}–${slotText(card.window.end)}`],['Suggested work',segments||'NOT_AVAILABLE'],['Agreed deadline',slotText(card.deadline_slot)],['Reviewer',card.reviewer??'Self-certifiable fixture policy'],['Next action',card.next_action]]){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=String(value);dl.append(dt,dd);}article.append(dl);$('cards').append(article);}
 renderProjectionGraph(projection);
 $('pov-raw').textContent=JSON.stringify(projection,null,2);
}
function renderTrace(){
 const filter=(id,value)=>!$(id).value||String(value).toLowerCase().includes($(id).value.toLowerCase());
 const rows=caseEvents().slice(0,position).filter(e=>filter('filter-approach',e.approach)&&filter('filter-actor',e.actor_id)&&filter('filter-role',e.actor_role)&&filter('filter-phase',e.phase)&&filter('filter-action',e.action_type)&&filter('filter-entity',e.affected_entity_refs.join(' '))&&filter('filter-visibility',e.visibility_labels.join(' ')));
 const maxPage=Math.max(0,Math.ceil(rows.length/100)-1);page=Math.min(page,maxPage);
 $('trace').replaceChildren();for(const row of rows.slice(page*100,page*100+100)){
 const div=document.createElement('button');div.className='event';div.style.width='100%';div.style.textAlign='left';for(const text of [String(row.sequence_number),row.approach+' / '+row.action_type,row.summary]){const span=document.createElement('span');span.textContent=text;div.append(span);}div.onclick=()=>{$('raw-event').textContent=JSON.stringify(row,null,2);$('raw-event').parentElement.open=true;};$('trace').append(div);}
 $('trace-count').textContent=`${rows.length} matching events · page ${page+1} / ${maxPage+1}`;$('trace-prev').disabled=page===0;$('trace-next').disabled=page>=maxPage;
}
function renderPosition(){
 const events=caseEvents();position=Math.min(position,events.length);$('scrubber').max=String(events.length);$('scrubber').value=String(position);
 $('progress').textContent=`${position} / ${events.length} events`;$('current-event').textContent=position?events[position-1].summary:'Initial snapshot. Step to inspect the first action.';
 $('step').disabled=position>=events.length;renderTrace();
}
function render(){
 $('scale').textContent=`${data.company.employees.toLocaleString()} employees · ${data.company.teams} teams · ${data.company.projects} projects · ${data.company.tasks.toLocaleString()} initial tasks · ${data.company.preset}`;
 $('case-label').textContent=(current().id==='A'||current().id==='B'?'CHANGE ':'SUPPORTING CASE · ')+current().id;$('summary').textContent=current().summary;
 $('case-a').textContent=data.cases[0]?`${data.cases[0].id} · ${data.cases[0].id==='A'?'Deadline pull-in':'Supporting case'}`:'No case';
 $('case-b').textContent=data.cases[1]?`${data.cases[1].id} · ${data.cases[1].id==='B'?'Critical incident':'Supporting case'}`:'No second case';
 $('case-a').classList.toggle('selected',caseIndex===0);$('case-b').classList.toggle('selected',caseIndex===1);$('case-b').disabled=data.cases.length<2;
 if($('case-picker').children.length!==data.cases.length){$('case-picker').replaceChildren();for(const item of data.cases){const option=make('option',`${item.id} · ${item.summary}`);option.value=item.id;$('case-picker').append(option);}}
 $('case-picker').value=current().id;$('case-picker-label').hidden=data.cases.length<3;
 $('outcomes').replaceChildren();for(const [method,record] of Object.entries(current().methods)){const d=document.createElement('div');d.className='outcome';d.textContent=`${method==='naive'?'Naive':'Authored replay'}: ${record.outcome.terminal} · ${record.outcome.violations} neutral violations`;$('outcomes').append(d);}
 $('run-id').textContent=data.run_id;renderMetrics();renderPosition();renderProjection();renderInspector();
}
async function load(){if(window.BENCHMARK_DATA){data=window.BENCHMARK_DATA;$('rerun').disabled=true;$('rerun').textContent='Offline replay · rerun with CLI';render();setStatus('Offline evidence replay. Product-connected comparison is NOT_RUN.');return;}const response=await fetch('/api/run');if(!response.ok)throw Error('Evidence is unavailable; inspect the retained manifest.');data=await response.json();$('rerun').textContent='Reset fixture & run '+data.cases.map(item=>item.id).join(' → ');render();setStatus('Ready. Product-connected comparison is NOT_RUN.');}
$('case-a').onclick=()=>selectCase(0);$('case-b').onclick=()=>selectCase(1);
$('case-picker').onchange=()=>{const index=data.cases.findIndex(item=>item.id===$('case-picker').value);if(index>=0)selectCase(index);};
$('reset').onclick=()=>{stop();position=0;page=0;renderPosition();setStatus('Replay cursor reset to the immutable start.');};
$('step').onclick=()=>{stop();position++;renderPosition();};$('pause').onclick=()=>{stop();setStatus('Playback paused. Recorded metrics are unchanged.');};
$('resume').onclick=()=>{stop();playing=true;setStatus('Inspecting recorded events. Playback speed is not benchmark latency.');const tick=()=>{if(!playing)return;position++;renderPosition();if(position>=caseEvents().length){stop();return;}frame=requestAnimationFrame(tick);};frame=requestAnimationFrame(tick);};
$('finish').onclick=()=>{stop();position=caseEvents().length;renderPosition();};$('scrubber').oninput=()=>{stop();position=Number($('scrubber').value);renderPosition();};
$('viewer').onchange=()=>{stop();renderProjection();};
function setInspectorMode(mode){inspectorMode=mode;$('directory-panel').hidden=mode!=='directory';$('graph-panel').hidden=mode!=='graph';$('directory-tab').classList.toggle('selected',mode==='directory');$('graph-tab').classList.toggle('selected',mode==='graph');if(mode==='graph')renderGraph();}
$('explorer-toggle').onclick=()=>{$('explorer').hidden=!$('explorer').hidden;$('explorer-toggle').textContent=$('explorer').hidden?'Open company & graph inspector':'Close company & graph inspector';if(!$('explorer').hidden)renderInspector();};
$('directory-tab').onclick=()=>setInspectorMode('directory');$('graph-tab').onclick=()=>setInspectorMode('graph');
for(const id of ['employee-search','employee-team','employee-role'])$(id).oninput=()=>{employeePage=0;renderEmployees();};
$('employee-prev').onclick=()=>{employeePage--;renderEmployees();};$('employee-next').onclick=()=>{employeePage++;renderEmployees();};
$('task-search').oninput=()=>{taskPage=0;renderTasks();};$('task-prev').onclick=()=>{taskPage--;renderTasks();};$('task-next').onclick=()=>{taskPage++;renderTasks();};
$('graph-method').onchange=renderGraph;$('graph-scope').onchange=renderGraph;
for(const id of ['filter-approach','filter-actor','filter-role','filter-phase','filter-action','filter-entity','filter-visibility'])$(id).oninput=()=>{page=0;renderTrace();};
$('trace-prev').onclick=()=>{page--;renderTrace();};$('trace-next').onclick=()=>{page++;renderTrace();};
for(const button of document.querySelectorAll('[data-bookmark]'))button.onclick=()=>{stop();const index=caseEvents().findIndex(e=>e.action_type===button.dataset.bookmark);if(index<0){setStatus('NOT_AVAILABLE — this stage has no recorded event.');return;}position=index+1;renderPosition();};
$('rerun').onclick=async()=>{stop();$('rerun').disabled=true;setStatus('Running a fresh synthetic A → B attempt from the initial fixture…');try{const r=await fetch('/api/reset-run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!r.ok)throw Error('Run unavailable; previous evidence retained.');caseIndex=0;position=0;await load();}catch(e){setStatus(e.message);}finally{$('rerun').disabled=false;}};
load().catch(e=>setStatus(e.message));
