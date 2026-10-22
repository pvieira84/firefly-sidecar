const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),calls=[],listeners=new Map();
  const get=id=>{
    if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',addEventListener(type,fn){listeners.set(id+':'+type,fn);}});
    return elements.get(id);
  };
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URLSearchParams,
    fetch:async path=>{
      calls.push(path);
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
  console.log('Initial automatic loading, cached navigation, and manual reload checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
