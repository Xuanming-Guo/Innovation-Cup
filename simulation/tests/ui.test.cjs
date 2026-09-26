// Pure interaction-logic tests with a minimal DOM double. NOT browser rendering QA.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

class Element {
 constructor(id=''){this.id=id;this.children=[];this.textContent='';this.value='';this.hidden=false;this.disabled=false;this.open=false;this.style={};this.dataset={};this.classList={toggle(){}};this.parentElement={open:false};}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 get text(){return this.textContent+this.children.map(x=>x.text??'').join(' ');}
}
const payloadFile=process.argv[2];
if(!payloadFile)throw Error('Provide a generated judge-data.json');
const payload=JSON.parse(fs.readFileSync(payloadFile));
function setup(){
 const elements=new Map();
 const get=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
 get('viewer').value='judge';
 get('explorer').hidden=true;get('graph-panel').hidden=true;
 let callbacks=new Map(),seq=0;
 const context={document:{getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>[]},
   window:{BENCHMARK_DATA:payload},console,
   requestAnimationFrame:cb=>{callbacks.set(++seq,cb);return seq;},cancelAnimationFrame:id=>callbacks.delete(id)};
 vm.createContext(context);vm.runInContext(fs.readFileSync('ui/app.js','utf8'),context);
 return {get,context,callbacks};
}
test('20 metric rows, honest labels and offline fallback',()=>{
 const {get}=setup();assert.equal(get('metrics').children.length,20);assert.match(get('metrics').text,/NOT_RUN/);
 assert.equal(get('rerun').disabled,true);assert.match(get('scale').text,/25 employees/);
});
test('step, pause, resume, reset and connected B selection',()=>{
 const {get,callbacks}=setup();get('step').onclick();assert.match(get('progress').text,/1 \/ /);
 get('resume').onclick();assert.equal(callbacks.size,1);get('pause').onclick();assert.equal(callbacks.size,0);
 get('reset').onclick();assert.match(get('progress').text,/0 \/ /);
 get('case-b').onclick();assert.equal(get('case-label').text,'CHANGE B');
 get('finish').onclick();assert.ok(get('trace').children.length>0);assert.ok(get('trace').children.length<=100);
});
test('employee projection hides judge trace and forbidden incident text',()=>{
 const {get}=setup();get('case-b').onclick();get('viewer').value='e0008';get('viewer').onchange();
 assert.equal(get('trace-section').hidden,true);assert.equal(get('story').hidden,true);assert.equal(get('scorecard').hidden,true);
 assert.equal(get('pov').hidden,false);assert.doesNotMatch(get('cards').text,/SSO|incident-declaration/);
 assert.doesNotMatch(get('pov-raw').text,/SSO|incident-declaration/);assert.match(get('pov-states').text,/NOT_AVAILABLE/);
});
test('filter, raw event and metric provenance controls',()=>{
 const {get}=setup();get('finish').onclick();get('filter-action').value='task_assigned';get('filter-action').oninput();
 assert.equal(get('trace').children.length,5);get('trace').children[0].onclick();assert.match(get('raw-event').text,/task_assigned/);
 get('metrics').children[0].children[0].children[0].onclick();assert.equal(get('metric-detail').open,true);assert.match(get('metric-json').text,/source_event_or_artifact_refs/);
});
test('synthetic company directory and relational graph remain separate from POVs',()=>{
 const {get}=setup();get('explorer-toggle').onclick();assert.equal(get('explorer').hidden,false);
 assert.match(get('explorer-notice').text,/NOT AN AUTHORISATION VIEW/);assert.equal(get('employee-directory').children.length,12);
 assert.match(get('employee-count').text,/25 of 25/);get('employee-search').value='security';get('employee-search').oninput();
 assert.match(get('employee-count').text,/of 25 fictional profiles/);assert.ok(get('employee-directory').children.length>0);
 get('graph-tab').onclick();assert.ok(get('graph-records').children.length>0);assert.match(get('graph-notice').text,/NOT A GRAPH DATABASE/);
 assert.match(get('graph-stats').text,/tasks considered/);
});
