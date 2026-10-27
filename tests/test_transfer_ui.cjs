const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
const elements=new Map(),listeners=new Map(),calls=[];
const get=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',showModal(){this.open=true},close(){this.open=false},addEventListener(type,fn){listeners.set(id+':'+type,fn)}});return elements.get(id)};
let type='withdrawal';
const ctx=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},Intl,URL,URLSearchParams,fetch:async(path,options)=>{
 const body=options?.body?JSON.parse(options.body):null;calls.push({path,body});let result;
 if(path==='/api/bootstrap')return new Promise(()=>{});
 if(path==='/api/validation/transfer-options')result={token:'preview',group_id:'100',group_title:'<Expense>',accounts:[{id:'1',name:'Bank'},{id:'3',name:'Savings'}],transactions:[{journal_id:'11',journal_count:2,group_id:'100',description:'One',amount:'10',currency_code:'EUR',type,source_id:'1',destination_id:'3'},{journal_id:'12',journal_count:2,group_id:'100',description:'Hidden split',amount:'2',currency_code:'EUR',type}]};
 else if(path==='/api/validation/convert-transfer')result={complete:true,converted:2};
 else if(path==='/api/validation')result={transactions:[],tag:'todo'};
 else throw Error(path);
 return {ok:true,json:async()=>result};
}});
vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),ctx);
vm.runInContext("config={firefly_public_url:'https://firefly.test',todo_tag:'todo'}",ctx);
await vm.runInContext("openTransfer('11')",ctx);
assert(get('transfer-dialog').open);assert(get('transfer-target').innerHTML.includes('Hidden split'));assert(get('transfer-target').innerHTML.includes('&lt;Expense&gt;'));
assert.equal(get('transfer-source').value,'1');assert.equal(get('transfer-destination').value,'');
assert(get('confirm-transfer').disabled);
get('transfer-destination').value='1';listeners.get('transfer-destination:change')();assert(get('confirm-transfer').disabled);
get('transfer-destination').value='3';listeners.get('transfer-destination:change')();assert(!get('confirm-transfer').disabled);
listeners.get('cancel-transfer:click')();assert.equal(calls.filter(c=>c.path.includes('convert-transfer')).length,0);
type='deposit';await vm.runInContext("openTransfer('11')",ctx);
assert.equal(get('transfer-source').value,'');assert.equal(get('transfer-destination').value,'3');
get('transfer-source').value='1';listeners.get('transfer-source:change')();await listeners.get('confirm-transfer:click')();
assert(!get('transfer-dialog').open);assert.deepEqual(calls.find(c=>c.path.includes('convert-transfer')).body,{token:'preview',source_id:'1',destination_id:'3'});
for(const kind of ['withdrawal','deposit','transfer']){
 ctx.kind=kind;vm.runInContext("validationRows=[{journal_id:'1',group_id:'1',journal_count:1,description:'Example',amount:'1',type:kind,currency_code:'EUR'}];renderValidation()",ctx);
 assert.equal(get('validation-rows').innerHTML.includes('data-transfer='),kind!=='transfer');
}
console.log('Transfer action eligibility, whole-group preview, account defaults, validation, cancellation and submission passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
