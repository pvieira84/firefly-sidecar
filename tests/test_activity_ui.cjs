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
  console.log('Activity filters, pagination, replacement rendering, boundary controls and reset passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
