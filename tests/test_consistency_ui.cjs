const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),listeners=new Map(),calls=[];let polls=0;
  const get=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',addEventListener(type,fn){listeners.set(id+':'+type,fn);}});return elements.get(id);};
  const inconsistent={group_id:'100',journal_id:'12',journal_count:3,description:'Expense <unsafe>',amount:'10',currency_code:'EUR',date:'2026-10-20',source_name:'Bank',destination_name:'Shop',reasons:['Refunded expense'],issues:['Category must be cleared'],check_errors:['<lookup failed>'],status:'inconsistent'};
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URL,URLSearchParams,setTimeout:fn=>fn(),fetch:async(path,options)=>{
    calls.push({path,options});let result;
    if(path==='/api/bootstrap')result={configured:true,csrf:'csrf',tag:'Reimburse',firefly_public_url:'https://firefly.example/finance'};
    else if(path==='/api/validation')result={transactions:[],tag:'todo'};
    else if(path==='/api/consistency/start')result={id:'job'};
    else if(path.startsWith('/api/consistency/status?')){
      polls++;result=polls===1?{state:'running',phase:'collecting',pages:1,total_pages:3,total:20}:polls===2?{state:'running',phase:'checking',checked:20,total:60,inconsistent:2}:{state:'complete',phase:'checking',checked:60,total:60,inconsistent:4};
    }else if(path.startsWith('/api/consistency/results?')){
      const q=new URL('https://x'+path).searchParams;
      const all=q.get('show')==='all';result={page:Number(q.get('page')),pages:3,total:all?60:30,checked:60,groups:50,applicable:40,inconsistent:30,incomplete:1,
        rows:all?[inconsistent,{...inconsistent,group_id:'301',description:'Already consistent',issues:[],check_errors:[],status:'consistent'}]:[inconsistent]};
    }else if(path==='/api/consistency/cancel')result={stopping:true};
    else throw Error(path);
    return {ok:true,json:async()=>result};
  }});
  vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),context);await new Promise(setImmediate);
  await vm.runInContext("view('consistency')",context);
  assert(!calls.some(call=>call.path.startsWith('/api/consistency')),'Navigation must not scan');
  get('consistency-tag').value='Reimburse';
  await listeners.get('consistency-filters:submit')({preventDefault(){}});
  const starts=()=>calls.filter(call=>call.path==='/api/consistency/start');
  assert.equal(starts().length,1);
  const body=JSON.parse(starts()[0].options.body);
  assert.equal(body.tag,'Reimburse');assert(!('limit' in body),'Display page size must not affect scan scope');
  assert.equal(polls,3);assert.equal(get('consistency-progress-bar').value,100);
  assert.equal(get('consistency-progress-label').textContent,'Check complete');
  assert(get('consistency-summary').textContent.includes('60 journals evaluated'));
  assert(get('consistency-results').innerHTML.includes('Expense &lt;unsafe&gt;'));
  assert(get('consistency-results').innerHTML.includes('https://firefly.example/finance/transactions/show/100'));
  assert(get('consistency-results').innerHTML.includes('Journal #12'));
  assert(get('consistency-results').innerHTML.includes('&lt;lookup failed&gt;'));
  await listeners.get('next-consistency:click')();
  assert(get('consistency-page').textContent.includes('Page 2 of 3'));
  await listeners.get('previous-consistency:click')();
  assert(get('consistency-page').textContent.includes('Page 1 of 3'));
  get('consistency-show').value='all';await listeners.get('consistency-show:change')();
  assert(get('consistency-results').innerHTML.includes('Already consistent'));
  get('consistency-limit').value='50';await listeners.get('consistency-limit:change')();
  assert(calls.at(-1).path.includes('limit=50'));
  assert.equal(starts().length,1,'Pagination and display changes must not rescan');
  vm.runInContext("consistencyRunning=true;consistencyJob='job'",context);
  await listeners.get('stop-consistency:click')();
  assert(calls.some(call=>call.path==='/api/consistency/cancel'));
  listeners.get('consistency-tag:change')();
  assert.equal(get('consistency-results').innerHTML,'');
  console.log('Full consistency scan, progress polling, cached result pagination, display filters, escaping and cancellation controls passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
