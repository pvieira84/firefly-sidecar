const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),listeners=new Map(),calls=[];
  const get=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',showModal(){this.open=true;},close(){this.open=false;},addEventListener(type,fn){listeners.set(id+':'+type,fn);}});return elements.get(id);};
  const row={journal_id:'11',transaction_journal_id:'11',journal_count:1,group_id:'100',type:'withdrawal',description:'Dinner <test>',amount:'30.00',currency_code:'EUR',currency_decimal_places:2,tags:['todo']};
  let fail=false;
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URL,URLSearchParams,fetch:async(path,options)=>{
    const body=options?.body?JSON.parse(options.body):undefined;calls.push({path,body});
    let result,ok=true;
    if(path==='/api/bootstrap')result={configured:true,tag:'Reimburse',todo_tag:'todo',firefly_public_url:'https://firefly.example'};
    else if(path==='/api/validation')result={transactions:[row],tag:'todo'};
    else if(path==='/api/validation/reimbursement-options')result={token:'preview',transaction:row};
    else if(path==='/api/validation/mark-reimbursement'){ok=!fail;result=ok?{complete:true}:{error:'Transaction changed'};}
    else throw new Error('Unexpected request '+path);
    return {ok,json:async()=>result};
  }});
  vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  await vm.runInContext("perform(()=>openReimbursement('11'))",context);
  assert.equal(get('reimbursement-dialog').open,true);
  assert.equal(get('reimbursement-value').value,'100');
  assert.equal(get('confirm-reimbursement').disabled,false);
  assert(get('reimbursement-target').innerHTML.includes('Dinner &lt;test&gt;'));
  assert(get('reimbursement-target').innerHTML.includes('https://firefly.example/transactions/show/100'));
  get('reimbursement-value').value='0';listeners.get('reimbursement-value:input')();
  assert.equal(get('confirm-reimbursement').disabled,true);
  get('reimbursement-mode').value='amount';get('reimbursement-value').value='10.00';listeners.get('reimbursement-value:input')();
  assert(get('reimbursement-preview').textContent.includes('New split: Reimbursement'));
  await listeners.get('confirm-reimbursement:click')();
  assert.equal(get('reimbursement-dialog').open,false);
  assert.deepEqual(calls.find(x=>x.path==='/api/validation/mark-reimbursement').body,{token:'preview',mode:'amount',value:'10.00'});
  await vm.runInContext("perform(()=>openReimbursement('11'))",context);
  fail=true;await listeners.get('confirm-reimbursement:click')();
  assert.equal(get('confirm-reimbursement').disabled,true);
  assert(get('reimbursement-status').textContent.includes('Transaction changed'));
  console.log('Reimbursement dialog defaults, validation, preview, parent link, submission and uncertain-save controls passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
