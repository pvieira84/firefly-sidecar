const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',innerHTML:'',addEventListener(){},removeAttribute(name){delete this[name]}});return elements.get(id)};
const ctx=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URL,URLSearchParams,fetch:()=>new Promise(()=>{})});
vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),ctx);
let revision='after-save',jobs=0,statusReply=null;
ctx.apiMock=async path=>{
 if(path==='/api/amazon/status')return statusReply?statusReply:{stored:172,not_enriched:161,revision};
 if(path==='/api/amazon/find-matches'){jobs++;return {id:'job'}};
 if(path.startsWith('/api/amazon/match-status'))return {state:'complete',phase:'matching',checked:172,total:172,result:{stored:172,not_enriched:161,revision,orders:[]}};
 throw Error(path);
};
vm.runInContext('api=apiMock;config={firefly_public_url:"https://firefly.test"};amazonRevision="before-save"',ctx);
await vm.runInContext('loadAmazon()',ctx);
await vm.runInContext('loadAmazonStatus()',ctx);
assert.equal(jobs,1,'The post-save refresh must not be repeated by the status poll');
assert.equal(vm.runInContext('amazonRevision',ctx),'after-save');
let resolveOld;statusReply=new Promise(resolve=>{resolveOld=resolve});
const oldPoll=vm.runInContext('loadAmazonStatus()',ctx);
revision='newer-save';await vm.runInContext('loadAmazon()',ctx);
resolveOld({stored:172,not_enriched:162,revision:'outdated'});await oldPoll;statusReply=null;
assert.equal(jobs,2,'An old status response cannot trigger a second search');
assert.equal(vm.runInContext('amazonRevision',ctx),'newer-save');
assert.equal(get('amazon-nav-count').textContent,'161','An old response cannot overwrite fresh counts');
await vm.runInContext('loadAmazonStatus()',ctx);assert.equal(jobs,2);
revision='new-import';await vm.runInContext('loadAmazonStatus()',ctx);
assert.equal(jobs,3,'A genuinely new inbox revision still triggers one search');
await vm.runInContext('loadAmazonStatus()',ctx);assert.equal(jobs,3);
get('amazon-dialog').open=true;revision='while-reviewing';await vm.runInContext('loadAmazonStatus()',ctx);assert.equal(jobs,3,'Polling does not search behind an open review');get('amazon-dialog').open=false;
await vm.runInContext('loadAmazonStatus()',ctx);assert.equal(jobs,4);
// A successful reviewed match updates all loaded views without another search.
const beforeLocal=jobs;
ctx.localResult={stored:172,not_enriched:162,orders:[
 {key:'selected',order:{key:'order-a'},enriched:false,candidates:[{journal_id:'11',group_id:'100',description:'Old'},{journal_id:'12',group_id:'100'}]},
 {key:'same-order-payment',order:{key:'order-a'},enriched:false,candidates:[{journal_id:'11',group_id:'100'}]},
 {key:'other-order',order:{key:'order-b'},enriched:false,candidates:[{journal_id:'11',group_id:'100'},{journal_id:'99',group_id:'100'}]}
]};
ctx.localPlan={key:'selected',order:{key:'order-a'},journal_id:'11',group_id:'100',group_title:'New title',description:'New description'};
vm.runInContext('amazonResult=localResult;renderAmazonOrders=()=>{}',ctx);
await vm.runInContext('completeAmazonMatchLocally(localPlan,"Edited notes")',ctx);
assert.equal(jobs,beforeLocal,'Save must not start a full match search');
assert(ctx.localResult.orders[0].enriched);assert(ctx.localResult.orders[1].enriched);assert(!ctx.localResult.orders[2].enriched);
assert.equal(ctx.localResult.orders[0].candidates[0].notes,'Edited notes');assert(ctx.localResult.orders[0].candidates[0].applied);
assert.equal(ctx.localResult.orders[0].candidates.length,1,'Other journals cannot be offered for the now assigned payment');
assert.equal(ctx.localResult.orders[2].candidates[0].group_title,'New title');
assert.equal(ctx.localResult.orders[1].candidates.length,0);
assert.deepEqual(ctx.localResult.orders[2].candidates.map(row=>row.journal_id),['99']);
assert.equal(get('amazon-nav-count').textContent,'161');
await vm.runInContext('loadAmazonStatus()',ctx);assert.equal(jobs,beforeLocal,'Post-save polling must not trigger a full search');
await vm.runInContext('completeAmazonMatchLocally(localPlan,"Edited notes")',ctx);assert.equal(ctx.localResult.not_enriched,161,'Repeating completion does not subtract again');
console.log('Amazon post-save refresh deduplication, stale poll protection, new import refresh and modal polling guards passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
