const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),listeners=new Map(),calls=[];
  const get=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',showModal(){this.open=true;},close(){this.open=false;},addEventListener(type,fn){listeners.set(id+':'+type,fn);}});return elements.get(id);};
  const rows=[{journal_id:'12',transaction_journal_id:'12',group_id:'100',type:'withdrawal',description:'Expense',amount:'15',currency_code:'EUR',tags:['todo'],source_name:'Bank',destination_name:'Shop',allowed_accounts:{source_id:['1'],destination_id:['2']}},
              {journal_id:'21',transaction_journal_id:'21',group_id:'200',type:'deposit',description:'Deposit',amount:'20',currency_code:'EUR',tags:['todo'],source_name:'Income',destination_name:'Bank',allowed_accounts:{source_id:['3'],destination_id:['1']}}];
  let fail=true;
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URL,URLSearchParams,
    fetch:async(path,options)=>{
      const body=options?.body?JSON.parse(options.body):undefined;calls.push({path,body});
      let result,ok=true;
      if(path==='/api/bootstrap')result={configured:true,tag:'Reimburse',todo_tag:'todo',firefly_public_url:'https://firefly.example'};
      else if(path==='/api/validation')result={transactions:rows,tag:'todo'};
      else if(path==='/api/validation/categorize-options')result={token:'cat-token',transactions:rows.filter(row=>body.journal_ids.includes(row.journal_id)),accounts:[{id:'1',name:'Bank',type:'asset'},{id:'2',name:'Shop',type:'expense'},{id:'3',name:'Income',type:'revenue'}],categories:[{id:'10',name:'Groceries'}],budgets:[{id:'11',name:'Food'}],bills:[{id:'12',name:'Subscription'}]};
      else if(path==='/api/validation/categorize'){
        ok=!(fail&&body.journal_id==='21');result=ok?{complete:true}:{error:'Rejected update'};
      }else throw new Error('Unexpected request '+path);
      return {ok,json:async()=>result};
    }});
  vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),context);
  await new Promise(setImmediate);
  vm.runInContext("validationSelected=new Set(['12','21']);",context);
  await listeners.get('categorize-selected:click')();
  assert.equal(get('categorize-dialog').open,true);
  assert.equal(get('apply-categorize').disabled,true);
  assert(get('categorize-targets').innerHTML.includes('https://firefly.example/transactions/show/100'));
  assert(!get('categorize-source').innerHTML.includes('value="1"'));
  assert.equal(get('categorize-budget').disabled,false);
  get('categorize-category').value='10';get('categorize-budget').value='11';
  listeners.get('categorize-category:change')();
  assert.equal(get('apply-categorize').disabled,false);
  await listeners.get('apply-categorize:click')();
  assert.equal(get('categorize-dialog').open,true);
  assert(get('categorize-status').textContent.includes('Rejected update'));
  assert.equal(vm.runInContext('categorizeIds.length',context),1);
  assert.equal(get('categorize-budget').disabled,true);
  assert(!vm.runInContext("validationSelected.has('12')",context));
  fail=false;
  await listeners.get('apply-categorize:click')();
  assert.equal(get('categorize-dialog').open,false);
  const writes=calls.filter(c=>c.path==='/api/validation/categorize');
  assert.equal(writes.length,3);
  assert.deepEqual(writes[0].body.changes,{category_id:'10',budget_id:'11'});
  console.log('Categorization dialog, unchanged defaults, account compatibility, bulk partial failure and retry checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
