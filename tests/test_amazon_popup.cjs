const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();const get=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,checked:false});return elements.get(id);};
const data={settings:{url:'https://sidecar.test',account:'personal',token:'x'.repeat(40)},status:'Sidecar import failed: invalid date',pending:{orders:[{}],url:'https://sidecar.test',account:'personal'}};
const calls=[];let changed;
const chrome={storage:{local:{get:async()=>data,set:async()=>{}},onChanged:{addListener:fn=>{changed=fn;}}},runtime:{sendMessage:async message=>{calls.push(message.action);data.status=message.action==='discard'?'Collected orders discarded.':'Synced 1 orders.';delete data.pending;return {success:true};}}};
const context=vm.createContext({document:{getElementById:get},chrome,URL,Date});
(async()=>{
 await vm.runInContext('(async()=>{'+fs.readFileSync('extensions/amazon-sync/popup.js','utf8')+'})()',context);
 const localDate=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;const today=new Date(),first=new Date(today);first.setDate(first.getDate()-14);
 assert.equal(get('start').value,localDate(first));assert.equal(get('end').value,localDate(today));
 assert.match(get('pending-info').textContent,/1 collected orders/);assert.equal(get('retry').disabled,false);assert.equal(get('discard').disabled,false);
 await get('retry').onclick();assert.equal(get('status').textContent,'Synced 1 orders.');assert.equal(get('retry').disabled,true);assert.equal(get('pending-info').textContent,'');
 data.pending={orders:[{},{}],url:'https://sidecar.test',account:'personal'};changed({pending:{newValue:data.pending}});assert.equal(get('discard').disabled,false);
 await get('discard').onclick();assert.equal(get('status').textContent,'Collected orders discarded.');assert.equal(get('discard').disabled,true);assert.deepEqual(calls,['retry','discard']);
 console.log('Amazon popup pending counts, retry/discard actions and retained outcome messages passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
