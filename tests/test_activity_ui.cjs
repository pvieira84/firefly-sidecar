const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),listeners=new Map(),calls=[];
  const get=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',showModal(){},close(){},addEventListener(type,fn){listeners.set(id+':'+type,fn);}});return elements.get(id);};
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URL,URLSearchParams,
    fetch:async(path)=>{
      calls.push(path);let result;
      if(path==='/api/bootstrap')result={configured:true,tag:'Reimburse',todo_tag:'todo'};
      else if(path==='/api/validation')result={transactions:[],tag:'todo'};
      else if(path.startsWith('/api/activity?')) {
        const q=new URL('https://test'+path).searchParams,offset=Number(q.get('offset')),limit=Number(q.get('limit'));
        const filtered=q.get('state')==='blocked',total=filtered?0:60;
        result={events:total?[{id:String(offset),created:'2026-10-23T10:00:00Z',action:'Delete transaction',method:'DELETE',path:'transactions/'+offset,state:'completed'}]:[],
          offset,limit,total,previous_offset:offset?offset-limit:null,next_offset:offset+limit<total?offset+limit:null,actions:['Delete transaction','<unsafe>']};
      } else throw Error(path);
      return {ok:true,json:async()=>result};
    }});
  vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),context);await new Promise(setImmediate);
  await vm.runInContext('loadActivity()',context);
  assert(get('activity-page').textContent.includes('Page 1 of 3'));
  assert.equal(get('previous-activity').disabled,true);
  assert(get('activity-action').innerHTML.includes('&lt;unsafe&gt;'));
  await listeners.get('more-activity:click')();
  assert(calls.at(-1).includes('offset=25'));
  assert.equal(vm.runInContext('activityEvents.length',context),1,'Pages replace rather than append');
  assert(get('activity-list').innerHTML.includes('transactions/25'));
  assert.equal(get('previous-activity').disabled,false);
  await listeners.get('previous-activity:click')();
  assert(calls.at(-1).includes('offset=0'));
  get('activity-state').value='blocked';get('activity-group').value='123';get('activity-start').value='2026-10-01';get('activity-limit').value='50';
  await listeners.get('activity-filters:submit')({preventDefault(){}});
  assert(calls.at(-1).includes('state=blocked'));assert(calls.at(-1).includes('group_id=123'));
  assert(calls.at(-1).includes('limit=50'));assert(calls.at(-1).includes('offset=0'));
  assert.equal(get('activity-page').textContent,'No matching changes');
  assert.equal(get('more-activity').hidden,true);assert.equal(get('previous-activity').disabled,true);
  await listeners.get('reset-activity-filters:click')();
  assert(get('activity-page').textContent.includes('Page 1 of 3'));
  assert.equal(get('activity-group').value,'');
  const saved={id:'old-plan',deposit:{group_id:'200',transaction_journal_id:'21',description:'Refund <unsafe>',amount:'10',date:'2026-10-20'},expenses:[{group_id:'100',journal_id:'11',amount:'10',currency_code:'EUR'}],total:'10',currency:'EUR',tag:'Reimburse',link_type:{inward:'related',outward:'related'}};
  const summary={entry_type:'reimbursement',plan_id:'old-plan',plan:saved,state:'partial',operation_state:'partial',created:'2026-10-23T10:00:00Z',result:{items:[{journal_id:'11',status:'failed',error:'<error>'}]}};
  const card=vm.runInContext('reimbursementActivityCard('+JSON.stringify(summary)+')',context);
  assert(card.includes('data-resume-reimbursement="old-plan"'));
  assert(card.includes('&lt;error&gt;'));
  assert(vm.runInContext('reimbursementActivityCard('+JSON.stringify({...summary,state:'completed'})+')',context).includes('Inspect & verify links'));
  context.fetch=async path=>{calls.push(path);assert(path.includes('/api/reimbursements/plan?plan_id=old-plan'));return {ok:true,json:async()=>saved};};
  await listeners.get('activity-list:click')({target:{closest:()=>({dataset:{resumeReimbursement:'old-plan'}})}});
  assert(get('review-content').innerHTML.includes('Refund &lt;unsafe&gt;'));

  const row=(group_id)=>({group_id,title:'Purchase <unsafe>',total:'10',currency:'EUR',date:'2026-10-20',tags:[],splits:[{journal_id:group_id,description:'Purchase',amount:'10',source:'Bank',destination:'Cash'}]});
  const gbitPlan={id:'saved-gbit',rows:{original_id:row('100'),new_id:row('300'),refund_id:row('200')},links:[{},{}]};
  context.gbitEvent={plan:gbitPlan,plan_id:'saved-gbit',operation_state:'complete',created:'2026-10-23T10:00:00Z'};
  const gbitCard=vm.runInContext('gbitActivityCard(gbitEvent)',context);
  assert(gbitCard.includes('data-activity-gbit="saved-gbit"'));
  assert(gbitCard.includes('Inspect & verify links'));
  assert(gbitCard.includes('Purchase &lt;unsafe&gt;'));
  context.fetch=async path=>{assert(path.includes('/api/gbit/plan?plan_id=saved-gbit'));return {ok:true,json:async()=>gbitPlan};};
  await listeners.get('activity-list:click')({target:{closest:selector=>selector==='[data-activity-gbit]'?{dataset:{activityGbit:'saved-gbit'}}:null}});
  assert(get('gbit-review-content').innerHTML.includes('deposit refunds expense'));
  console.log('Activity filters, pagination, replacement rendering, boundary controls and reset passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
