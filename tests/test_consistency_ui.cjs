const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
  const elements=new Map(),listeners=new Map(),calls=[];
  const get=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',addEventListener(type,fn){listeners.set(id+':'+type,fn);}});return elements.get(id);};
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URL,URLSearchParams,fetch:async(path,options)=>{
    calls.push({path,options});let result;
    if(path==='/api/bootstrap')result={configured:true,tag:'Reimburse',firefly_public_url:'https://firefly.example/finance'};
    else if(path==='/api/validation')result={transactions:[],tag:'todo'};
    else if(path.startsWith('/api/consistency?')){
      const query=new URL('https://example'+path).searchParams;
      result={page:Number(query.get('page')),next_page:query.get('page')==='1'?2:null,groups:2,checked:3,applicable:1,
        findings:[{group_id:'100',journal_id:'12',journal_count:3,description:'Expense <unsafe>',amount:'10',currency_code:'EUR',date:'2026-10-20',source_name:'Bank',destination_name:'Shop',reasons:['Refunded expense'],issues:['Category must be cleared']}],
        errors:[{group_id:'200',journal_id:'21',error:'<lookup failed>'}]};
    }else throw Error(path);
    return {ok:true,json:async()=>result};
  }});
  vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),context);await new Promise(setImmediate);
  await vm.runInContext("view('consistency')",context);
  assert(!calls.some(call=>call.path.startsWith('/api/consistency')),'Navigation must not start a scan');
  get('consistency-tag').value='Reimburse';
  await listeners.get('consistency-filters:submit')({preventDefault(){}});
  const first=calls.find(call=>call.path.startsWith('/api/consistency'));
  assert.equal(new URL('https://x'+first.path).searchParams.get('limit'),'25');
  assert.equal(new URL('https://x'+first.path).searchParams.get('tag'),'Reimburse');
  assert.equal(first.options?.method,undefined,'Scan must be read-only');
  assert(get('consistency-results').innerHTML.includes('Expense &lt;unsafe&gt;'));
  assert(get('consistency-results').innerHTML.includes('https://firefly.example/finance/transactions/show/100'));
  assert(get('consistency-results').innerHTML.includes('Journal #12'));
  assert(get('consistency-results').innerHTML.includes('&lt;lookup failed&gt;'));
  assert(get('consistency-summary').textContent.includes('1 incomplete checks'));
  assert.equal(get('next-consistency').disabled,false);
  await listeners.get('next-consistency:click')();
  assert.equal(get('next-consistency').disabled,true);
  assert(get('consistency-summary').textContent.includes('Page 2'));
  listeners.get('consistency-tag:change')();
  assert.equal(get('consistency-results').innerHTML,'');
  assert.equal(get('next-consistency').disabled,true);
  console.log('Consistency scan requires explicit action, preserves filters, escapes results, links parents, handles incomplete checks and bounds pagination.');
})().catch(error=>{console.error(error);process.exitCode=1;});
