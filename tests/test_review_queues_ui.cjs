const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),listeners=new Map(),calls=[];
  const get=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',addEventListener(type,fn){listeners.set(id+':'+type,fn);}});return elements.get(id);};
  const row=(journal_id,tags)=>({group_id:'100',journal_id,journal_count:3,group_title:'Dinner',description:'Purchase',tags,amount:'10',currency_code:'EUR',date:'2026-10-20',type:'withdrawal'});
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URL,URLSearchParams,fetch:async(path,options)=>{
    calls.push({path,options});let result;
    if(path==='/api/bootstrap')result={configured:true,tag:'Reimburse',todo_tag:'todo',firefly_public_url:'https://firefly.example'};
    else if(path.startsWith('/api/validation')){
      const queue=new URL('https://x'+path).searchParams.get('queue')||'todo';
      result={tag:{todo:'todo',reimbursements:'Reimburse',gbit:'#GBIT'}[queue],transactions:queue==='todo'?[row('11',['todo'])]:queue==='reimbursements'?[row('12',['Reimburse']),row('13',['todo','Reimburse'])]:[row('14',['#GBIT'])]};
    }else throw Error(path);
    return {ok:true,json:async()=>result};
  }});
  vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),context);await new Promise(setImmediate);
  assert(calls.some(call=>call.path==='/api/validation'));
  vm.runInContext("validationSelected.add('11')",context);
  get('validation-queue').value='reimbursements';await listeners.get('validation-queue:change')();
  assert(calls.some(call=>call.path==='/api/validation?queue=reimbursements'));
  assert.equal(vm.runInContext('validationSelected.size',context),0);
  assert.equal(get('todo-tag').textContent,'Reimburse');
  vm.runInContext("updateValidatedReview(null,'13');renderValidation()",context);
  assert.equal(vm.runInContext('validationRows.length',context),2);
  assert.equal(vm.runInContext("validationRows.find(row=>row.journal_id==='13').tags.join(',')",context),'Reimburse');
  get('validation-queue').value='gbit';await listeners.get('validation-queue:change')();
  assert.equal(get('todo-tag').textContent,'#GBIT');
  assert.equal(vm.runInContext('validationRows[0].journal_id',context),'14');

  const beforePeriod=calls.length;
  get('validation-queue').value='period';await listeners.get('validation-queue:change')();
  assert.equal(calls.length,beforePeriod,'Selecting Period must not fetch transactions');
  assert.equal(get('validation-start-field').hidden,false);
  const today=new Date(),start=new Date(today);start.setDate(start.getDate()-7);
  const localDate=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  assert.equal(get('validation-start').value,localDate(start));
  assert.equal(get('validation-end').value,localDate(today));
  await vm.runInContext("autoLoadedTools.delete('validation');view('validation')",context);
  assert.equal(calls.length,beforePeriod,'Navigation must not load an unrequested period');
  get('validation-start').value='2026-10-01';get('validation-end').value='2026-10-26';
  listeners.get('validation-start:change')();
  assert.equal(calls.length,beforePeriod,'Editing dates must not fetch');
  await listeners.get('load-validation:click')();
  assert(calls.at(-1).path.includes('queue=period&start=2026-10-01&end=2026-10-26'));
  get('validation-queue').value='todo';await listeners.get('validation-queue:change')();
  vm.runInContext("updateValidatedReview(null,'11')",context);
  assert.equal(vm.runInContext('validationRows.length',context),0);
  console.log('Review Todo default, reimbursement/GBIT queue loading, selection reset and validation tag semantics passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
