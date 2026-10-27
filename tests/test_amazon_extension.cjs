const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
const values={settings:{url:'https://sidecar.test/finance',token:'secret'.repeat(8),account:'household',daily:true}};
const listeners={};const requests=[];let fail=false;
const event=name=>({addListener:fn=>{listeners[name]=fn;}});
const browser={runtime:{id:'companion',onMessage:event('message'),onStartup:event('startup')},storage:{local:{get:async key=>typeof key==='string'?{[key]:values[key]}:Object.fromEntries(key.map(k=>[k,values[k]])),set:async data=>Object.assign(values,data),remove:async keys=>{for(const key of [].concat(keys))delete values[key];}},session:{setAccessLevel:async()=>{}}},tabs:{create:async()=>({id:1}),update:async()=>{},sendMessage:async()=>({success:true}),onUpdated:event('updated'),onRemoved:event('removed')},alarms:{create:async()=>{},clear:async()=>{},onAlarm:event('alarm')}};
const context=vm.createContext({browser,fetch:async(url,options)=>{requests.push({url,options});return {ok:!fail,status:fail?503:200};},Date,Error,console});
vm.runInContext(fs.readFileSync('extensions/amazon-sync/background.js','utf8').replace("import browser from 'webextension-polyfill';",''),context);
const popup={id:'companion'};const tab={id:'companion',tab:{id:1,url:'https://www.amazon.es/gp/your-account/order-history'}};
(async()=>{
 let result=await listeners.message({action:'sync',start:'2026-10-01',end:'2026-10-27'},popup);assert.equal(result.success,true);assert.equal(values.job.tabId,1);
 assert.equal(listeners.message({action:'sidecarOrders',orders:[]},{tab:{id:9,url:'https://evil.test/'}}),undefined);
 fail=true;result=await listeners.message({action:'sidecarOrders',orders:[{orderId:'test'}]},tab);assert.equal(result.success,false);assert.ok(values.pending);
 fail=false;result=await listeners.message({action:'retry'},popup);assert.equal(result.success,true);assert.equal(values.pending,undefined);assert.equal(values.job,undefined);
 assert.equal(requests[0].url,'https://sidecar.test/finance/api/amazon/import');assert.equal(requests[0].options.redirect,'error');assert.equal(requests[0].options.credentials,'omit');assert.equal(JSON.parse(requests[0].options.body).account,'household');
 assert.equal(requests[0].options.headers.Authorization,'Bearer '+values.settings.token);
 await listeners.startup();console.log('Amazon extension scheduling, scoped submission and retry checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
