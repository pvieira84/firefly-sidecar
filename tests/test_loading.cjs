const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),calls=[],listeners=new Map();
  const get=id=>{
    if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',showModal(){this.open=true;},close(){this.open=false;},addEventListener(type,fn){listeners.set(id+':'+type,fn);}});
    return elements.get(id);
  };
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URLSearchParams,
    fetch:async (path,options)=>{
      calls.push(path);
      if(path==='/api/validation/mark-cash') {
        const body=JSON.parse(options.body);
        return {ok:body.journal_id!=='12',json:async()=>body.journal_id==='12'?{error:'Cash update failed'}:{complete:true}};
      }
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
  const originalFetch=context.fetch;
  let duplicatePage=0;const pageRequests=[];
  const row={group_id:'1',title:'Example',date:'2026-09-23',type:'deposit',total:'0.55',currency:'EUR',tags:[],splits:[]};
  context.fetch=async path=>{pageRequests.push(path);duplicatePage++;return {ok:true,json:async()=>({scanned:36,skipped:[],pairs:[{left:{...row,group_id:String(duplicatePage)},right:{...row,group_id:String(duplicatePage+100)},days_apart:0,signals:[]}],next_offset:duplicatePage===1?500:null})};};
  await listeners.get('load-duplicates:click')();
  assert.equal(get('more-duplicates').hidden,false);
  assert(get('duplicates-summary').textContent.includes('more available'));
  const originalStart=get('duplicates-start').value;
  get('duplicates-start').value='2020-01-01';
  await listeners.get('more-duplicates:click')();
  assert(pageRequests[1].includes('start='+originalStart));
  assert(pageRequests[1].includes('offset=500'));
  assert.equal(get('more-duplicates').hidden,true);
  assert(get('duplicates-summary').textContent.includes('2 candidate pairs shown'));
  context.fetch=originalFetch;
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
  vm.runInContext("validationRows=[{journal_id:'11',group_id:'100',description:'First',amount:'10',currency_code:'EUR'},{journal_id:'12',group_id:'101',description:'Second',amount:'20',currency_code:'EUR'}];validationSelected=new Set(['11','12']);renderValidation()",context);
  await listeners.get('cash-selected:click')();
  assert(get('message').textContent.includes('1 transaction marked as cash'));
  assert(get('message').textContent.includes('Cash update failed'));
  assert(calls.includes('/api/validation/mark-cash'));
  const refundCalls=[];
  context.fetch=async(path,options)=>{
    const body=options?JSON.parse(options.body):null;refundCalls.push({path,body});
    return {ok:true,json:async()=>path==='/api/validation/refund-candidates'?{token:'search-token',deposit:{group_id:'200',description:'Refund',amount:'20',currency_code:'EUR',date:'2026-10-22'},start:'2026-07-24',end:'2026-10-22',tolerance:'1.00',same_account:true,skipped:[],candidates:[{group_id:'100',title:'Dinner',date:'2026-10-20',type:'withdrawal',total:'20',currency:'EUR',tags:[],splits:[],difference:'0'}]}:path==='/api/validation/mark-refund'?{links:1,todo_removed:true}:{transactions:[],tag:'todo'}};
  };
  await vm.runInContext("perform(()=>openRefund('21'))",context);
  assert.equal(get('refund-dialog').open,true);
  assert.equal(get('refund-same-account').checked,true);
  assert.equal(refundCalls[0].body.same_account,true);
  assert.equal(get('confirm-refund').disabled,true);
  assert.equal(get('refund-start').value,'2026-07-24');
  await listeners.get('refund-candidates:change')({target:{name:'refund-withdrawal',value:'100'}});
  assert.equal(get('confirm-refund').disabled,false);
  get('refund-remove-todo').checked=true;
  await listeners.get('confirm-refund:click')();
  assert.equal(refundCalls.find(c=>c.path==='/api/validation/mark-refund').body.remove_todo,true);
  assert.equal(get('refund-dialog').open,false);
  console.log('Refund dialog search, selection, confirmation and todo option checks passed.');
  console.log('Multi-selection, filtered select-all, partial bulk failure and clearing checks passed.');
  console.log('Initial automatic loading, cached navigation, and manual reload checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
