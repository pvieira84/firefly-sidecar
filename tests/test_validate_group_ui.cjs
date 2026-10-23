const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),listeners=new Map(),calls=[];
  const get=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',addEventListener(type,fn){listeners.set(id+':'+type,fn);}});return elements.get(id);};
  let fail=false;
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URL,URLSearchParams,fetch:async(path,options)=>{
    if(path==='/api/bootstrap')return new Promise(()=>{});
    calls.push({path,body:JSON.parse(options.body)});
    assert.equal(path,'/api/validation/complete-group');
    return {ok:!fail,json:async()=>fail?{error:'Write failed'}:{complete:true,validated:2}};
  }});
  vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),context);
  vm.runInContext(`config={csrf:'test'};validationLoaded=true;validationRows=[
    {journal_id:'11',group_id:'100',journal_count:3,description:'Shown',tags:['todo'],amount:'10',currency_code:'EUR'},
    {journal_id:'12',group_id:'100',journal_count:3,description:'Hidden',tags:['todo'],amount:'20',currency_code:'EUR'},
    {journal_id:'21',group_id:'200',journal_count:1,description:'Other',tags:['todo'],amount:'30',currency_code:'EUR'}];
    validationSelected=new Set(['11','12','21']);`,context);
  get('validation-search').value='Shown';vm.runInContext('renderValidation()',context);
  assert(get('validation-rows').innerHTML.includes('data-validate-group="100"'));
  assert(get('validation-rows').innerHTML.includes('all pending splits'));
  const click=()=>listeners.get('validation-rows:click')({target:{closest:selector=>selector==='[data-validate-group]'?{dataset:{validateGroup:'100'}}:null}});
  fail=true;click();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(vm.runInContext('validationRows.length',context),3);
  fail=false;click();await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(calls[1],{path:'/api/validation/complete-group',body:{group_id:'100'}});
  assert.equal(vm.runInContext('validationRows.length',context),1);
  assert.equal(vm.runInContext('validationSelected.size',context),1);
  assert.equal(vm.runInContext("validationSelected.has('21')",context),true);
  get('validation-search').value='';vm.runInContext('renderValidation()',context);
  assert(!get('validation-rows').innerHTML.includes('data-validate-group'));
  assert(get('validation-rows').innerHTML.includes('data-validate="21"'));
  console.log('Parent validation covers hidden splits, preserves other transactions and selections, and keeps rows on failure.');
})().catch(error=>{console.error(error);process.exitCode=1;});
