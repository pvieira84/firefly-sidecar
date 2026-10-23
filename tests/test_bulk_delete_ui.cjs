const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),listeners=new Map(),calls=[];
  const get=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',showModal(){this.open=true;},close(){this.open=false;},addEventListener(type,fn){listeners.set(id+':'+type,fn);}});return elements.get(id);};
  const rows=[['11','100'],['12','100'],['21','200'],['31','300']].map(([journal_id,group_id])=>({journal_id,group_id,description:'Purchase',amount:'10',currency_code:'EUR',type:'withdrawal',tags:['todo']}));
  let remaining=[...rows],fail='';
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URL,URLSearchParams,
    fetch:async(path,options)=>{
      const body=options?.body?JSON.parse(options.body):undefined;calls.push({path,body});
      if(path==='/api/validation/delete-preview')return {ok:true,json:async()=>({token:body.group_id,group_id:body.group_id,transaction:{attributes:{group_title:'Expense <test>',transactions:[{transaction_journal_id:'11',description:'Purchase',amount:'10',currency_code:'EUR'},{transaction_journal_id:'12',description:'Unselected fee',amount:'1',currency_code:'EUR'}]}}})};
      if(path==='/api/validation/delete') {
        if(body.token===fail)return {ok:false,json:async()=>({error:'Transaction changed'})};
        remaining=remaining.filter(row=>row.group_id!==body.token);
        return {ok:true,json:async()=>({deleted:true,group_id:body.token})};
      }
      return {ok:true,json:async()=>path==='/api/bootstrap'?{configured:true,tag:'Reimburse',todo_tag:'todo',firefly_public_url:'https://firefly.example'}:{transactions:remaining,tag:'todo'}};
    }});
  vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),context);
  await new Promise(setImmediate);
  vm.runInContext("validationSelected=new Set(['11','12','21']);renderValidation()",context);
  assert.equal(get('delete-selected').disabled,false);
  await listeners.get('delete-selected:click')();
  assert.equal(calls.filter(c=>c.path.endsWith('delete-preview')).length,2,'Deduplicate selected siblings');
  assert.equal(calls.filter(c=>c.path.endsWith('/delete')).length,0,'Preview must never delete');
  assert(get('delete-content').innerHTML.includes('Unselected fee'));
  assert(get('delete-content').innerHTML.includes('even unselected splits'));
  assert(get('delete-content').innerHTML.includes('Expense &lt;test&gt;'));
  listeners.get('cancel-delete:click')();
  assert.equal(get('delete-dialog').open,false);
  assert.equal(calls.filter(c=>c.path.endsWith('/delete')).length,0);
  await listeners.get('delete-selected:click')();
  await listeners.get('confirm-delete:click')();
  assert.deepEqual(calls.filter(c=>c.path.endsWith('/delete')).map(c=>c.body.token),['100','200']);
  assert.equal(vm.runInContext('validationSelected.size',context),0);
  assert(get('message').textContent.includes('2 of 2'));
  // Stop on a failure; do not retry it or proceed to later transactions.
  remaining=[...rows];fail='200';await vm.runInContext('loadValidation()',context);
  vm.runInContext("validationSelected=new Set(['11','21','31']);renderValidation()",context);
  const before=calls.length;
  await listeners.get('delete-selected:click')();await listeners.get('confirm-delete:click')();
  assert.deepEqual(calls.slice(before).filter(c=>c.path.endsWith('/delete')).map(c=>c.body.token),['100','200']);
  assert.equal(vm.runInContext("validationSelected.has('11')",context),false);
  assert.equal(vm.runInContext("validationSelected.has('21')&&validationSelected.has('31')",context),true);
  assert(get('message').textContent.includes('1 of 3'));
  assert(get('message').textContent.includes('Inspect Activity'));
  console.log('Bulk delete preview, cancellation, sibling deduplication, full-parent disclosure and partial-failure stop passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
