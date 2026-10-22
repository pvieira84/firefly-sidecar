const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),calls=[],listeners=new Map();
  const get=id=>{
    if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',addEventListener(type,fn){listeners.set(id+':'+type,fn);}});
    return elements.get(id);
  };
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URLSearchParams,
    fetch:async (path,options)=>{
      calls.push(path);
      if(path==='/api/validation/complete') {
        const body=JSON.parse(options.body);
        return {ok:body.journal_id!=='12',json:async()=>body.journal_id==='12'?{error:'Tag update failed'}:{complete:true}};
      }
      const data=path==='/api/bootstrap'?{configured:true,tag:'Reimburse',todo_tag:'todo'}:
        path==='/api/validation'?{transactions:[],tag:'todo'}:path.startsWith('/api/duplicates?')?{scanned:0,pairs:[],skipped:[],truncated:false}:{deposits:[],expenses:[]};
      return {ok:true,json:async()=>data};
    }});
  vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),context);
  await new Promise(setImmediate);
  assert.deepEqual(calls,['/api/bootstrap','/api/validation']);
  await vm.runInContext("view('reimbursements')",context);
  assert.equal(calls.filter(x=>x.startsWith('/api/reimbursements?')).length,1);
  await vm.runInContext("view('validation');view('reimbursements')",context);
  assert.equal(calls.length,3);
  get('start').value='2026-10-01';get('end').value='2026-10-10';
  await listeners.get('filter-dates:click')();
  assert.equal(calls.at(-1),'/api/reimbursements?start=2026-10-01&end=2026-10-10');
  await listeners.get('load-validation:click')();
  assert.equal(calls.filter(x=>x==='/api/validation').length,2);
  get('duplicates-days').value='3';
  await vm.runInContext("view('duplicates')",context);
  assert.equal(calls.filter(x=>x.startsWith('/api/duplicates?')).length,1);
  await vm.runInContext("view('validation');view('duplicates')",context);
  assert.equal(calls.filter(x=>x.startsWith('/api/duplicates?')).length,1);
  get('duplicates-days').value='0';
  await listeners.get('load-duplicates:click')();
  assert(calls.at(-1).endsWith('&days=0'));
  vm.runInContext(`validationRows=[{journal_id:'11',group_id:'100',description:'First',tags:['todo'],amount:'10',currency_code:'EUR'},{journal_id:'12',group_id:'101',description:'Second',tags:['todo'],amount:'20',currency_code:'EUR'}];renderValidation()`,context);
  get('validation-search').value='first';
  await listeners.get('validation-select-all:change')({target:{checked:true}});
  assert.equal(vm.runInContext('validationSelected.size',context),1);
  get('validation-search').value='';
  await listeners.get('validation-select-all:change')({target:{checked:true}});
  assert.equal(vm.runInContext('validationSelected.size',context),2);
  get('validation-search').value='first';vm.runInContext('renderValidation()',context);
  assert.equal(get('validation-selection-count').textContent,'2 selected (1 visible)');
  await listeners.get('validate-selected:click')();
  assert.equal(vm.runInContext('validationSelected.size',context),1);
  assert(vm.runInContext("validationSelected.has('12')",context));
  assert.equal(vm.runInContext('validationRows.length',context),1);
  assert(get('message').textContent.includes('1 failed and remain selected'));
  assert(get('message').textContent.includes('Tag update failed'));
  await listeners.get('clear-validation-selection:click')();
  assert.equal(vm.runInContext('validationSelected.size',context),0);
  assert.equal(get('validate-selected').disabled,true);
  console.log('Multi-selection, filtered select-all, partial bulk failure and clearing checks passed.');
  console.log('Initial automatic loading, cached navigation, and manual reload checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
