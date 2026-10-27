const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(),listeners=new Map();
const get=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',innerHTML:'',disabled:false,hidden:false,addEventListener:(name,fn)=>listeners.set(id+':'+name,fn),showModal(){this.open=true;},close(){this.open=false;}});return elements.get(id);};
const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},fetch:()=>new Promise(()=>{}),Intl,URL,URLSearchParams});
vm.runInContext(fs.readFileSync('sidecar/static/app.js','utf8'),context);
context.journal={group_id:'100',journal_id:'11',journal_count:3,description:'Original <purchase>',date:'2026-10-20',source_name:'Bank',destination_name:'Amazon',amount:'30.00',currency_code:'EUR'};context.calls=[];
vm.runInContext(`config={csrf:'test',firefly_public_url:'https://firefly.test'};
api=async(path,body)=>{calls.push({path,body});if(path.endsWith('manual-options'))return {journals:[journal],gift_card_configured:true};if(path.endsWith('gift-review'))return {id:'gift-plan',original:journal,transaction:{description:journal.description,amount:body.amount},group_id:'100',journal_id:'11',journal_count:3,account:{attributes:{name:'Gift <card>'}},tag:'Gift Paid'};if(path.endsWith('manual-review'))return {id:'manual-plan',rows:[journal],total:'30',order_total:'45',currency:'EUR',description:'Amazon order'};if(path.endsWith('gift-apply'))return {complete:true,group_id:'300'};return {stored:1,orders:[]};};`,context);
(async()=>{
 await vm.runInContext("openAmazonManual('order-key')",context);
 assert.match(get('amazon-manual-journals').innerHTML,/Journal #11/);assert.match(get('amazon-manual-journals').innerHTML,/transactions\/show\/100/);assert.doesNotMatch(get('amazon-manual-journals').innerHTML,/<purchase>/);
 listeners.get('amazon-manual-journals:change')({target:{dataset:{amazonPaying:'11'},checked:true}});assert.equal(get('amazon-gift-amount').value,'30.00');
 get('amazon-gift-amount').value='12.34';await vm.runInContext('reviewAmazonManual(true)',context);
 assert.equal(context.calls.find(c=>c.path.endsWith('gift-review')).body.amount,'12.34');assert.match(get('amazon-manual-preview').innerHTML,/12.34/);assert.match(get('amazon-manual-preview').innerHTML,/Gift &lt;card&gt;/);assert.match(get('amazon-manual-preview').innerHTML,/Related/);
 await listeners.get('amazon-manual-apply:click')();assert.match(get('amazon-manual-status').innerHTML,/transactions\/show\/300/);
 await vm.runInContext("openAmazonManual('order-key')",context);listeners.get('amazon-manual-journals:change')({target:{dataset:{amazonPaying:'11'},checked:true}});
 await vm.runInContext('reviewAmazonManual(false)',context);assert.match(get('amazon-manual-preview').innerHTML,/totals differ/);assert.equal(context.calls.find(c=>c.path.endsWith('manual-review')).body.journal_ids[0],'11');
 console.log('Amazon manual journal selection, editable gift amount, mismatch review, safe links and creation controls passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
