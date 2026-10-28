const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
const values={settings:{url:'https://sidecar.test/finance',token:'secret'.repeat(8),account:'household',daily:true}};
const listeners={};const requests=[];const starts=[];const closed=[];let fail=false;
const event=name=>({addListener:fn=>{listeners[name]=fn;}});
const browser={runtime:{id:'companion',onMessage:event('message'),onStartup:event('startup')},storage:{local:{get:async key=>typeof key==='string'?{[key]:values[key]}:Object.fromEntries(key.map(k=>[k,values[k]])),set:async data=>Object.assign(values,data),remove:async keys=>{for(const key of [].concat(keys))delete values[key];}},session:{setAccessLevel:async()=>{}}},tabs:{get:async id=>({id,url:'https://www.amazon.es/gp/your-account/order-history'}),remove:async id=>{closed.push(id);await listeners.removed(id);},create:async()=>({id:1}),update:async()=>{},sendMessage:async(id,message)=>{starts.push({id,message});return {success:true};},onUpdated:event('updated'),onRemoved:event('removed')},alarms:{create:async()=>{},clear:async()=>{},onAlarm:event('alarm')}};
const context=vm.createContext({browser,fetch:async(url,options)=>{requests.push({url,options});return {ok:!fail,status:fail?503:200,json:async()=>({error:'Invalid Amazon date. '+values.settings.token})};},Date,Error,console,URL});
vm.runInContext(fs.readFileSync('extensions/amazon-sync/background.js','utf8').replace("import browser from 'webextension-polyfill';",''),context);
const popup={id:'companion'};const tab={id:'companion',tab:{id:1,url:'https://www.amazon.es/gp/your-account/order-history'}};
(async()=>{
 let result=await listeners.message({action:'sync',start:'2026-10-01',end:'2026-10-27'},popup);assert.equal(result.success,true);assert.equal(values.job.tabId,1);
 // Chrome may omit tab.url; sender.url identifies the loaded document.
 const english={id:'companion',url:'https://www.amazon.es/-/en/your-orders/orders?ref_=nav_orders_first',tab:{id:1}};
 await listeners.message({action:'collectorReady',page:'other'},{...english,url:'https://www.amazon.es/'});
 assert.ok(values.job);assert.equal(starts.length,0);
 await listeners.message({action:'collectorReady',page:'auth'},{...english,url:'https://www.amazon.es/ap/signin'});
 assert.ok(values.job);assert.equal(starts.length,0);
 await listeners.message({action:'collectorReady',page:'orders'},{...english,tab:{id:99}});
 assert.equal(starts.length,0);
 await listeners.message({action:'collectorReady',page:'orders'},english);
 assert.equal(starts.length,1);assert.equal(starts[0].message.options.includeTransactions,true);
 assert.equal(starts[0].message.options.startDate,'2026-10-01');
 await listeners.message({action:'collectorReady',page:'orders'},english);assert.equal(starts.length,1);
 assert.equal(listeners.message({action:'sidecarOrders' ,orders:[]},{tab:{id:9,url:'https://evil.test/'}}),undefined);
 fail=true;result=await listeners.message({action:'sidecarOrders',orders:[{orderId:'test'}]},english);assert.equal(result.success,false);assert.ok(values.pending);assert.equal(closed.length,0);
 assert.match(result.error,/Invalid Amazon date/);assert.ok(!result.error.includes(values.settings.token));
 const queued=values.pending;
 result=await listeners.message({action:'stop'},popup);assert.equal(result.success,true);assert.equal(values.pending,queued);assert.equal(values.job,undefined);assert.match(values.status,/kept/);
 result=await listeners.message({action:'sync',start:'2026-10-01',end:'2026-10-27'},popup);assert.equal(result.success,false);assert.match(result.error,/Invalid Amazon date/);assert.match(result.error,/Discard collected orders/);
 result=await listeners.message({action:'discard'},popup);assert.equal(result.success,true);assert.equal(values.pending,undefined);assert.equal(values.settings.account,'household');
 result=await listeners.message({action:'sync',start:'2026-10-01',end:'2026-10-27'},popup);assert.equal(result.success,true);assert.ok(values.job);
 fail=true;result=await listeners.message({action:'sidecarOrders',orders:[{orderId:'test'}]},english);assert.equal(result.success,false);assert.ok(values.pending);

 fail=false;result=await listeners.message({action:'retry'},popup);assert.equal(result.success,true);assert.equal(values.pending,undefined);assert.equal(values.job,undefined);assert.deepEqual(closed,[1]);assert.match(values.status,/Synced/);
 assert.equal(requests[0].url,'https://sidecar.test/finance/api/amazon/import');assert.equal(requests[0].options.redirect,'error');assert.equal(requests[0].options.credentials,'omit');assert.equal(JSON.parse(requests[0].options.body).account,'household');
 assert.equal(requests[0].options.headers.Authorization,'Bearer '+values.settings.token);
 // The readiness probe recognizes URL structure, independent of page language.
 for(const [pathname,expected] of [
  ['/-/en/your-orders/orders','orders'],['/-/es/gp/your-account/order-history/ref=abc','orders'],
  ['/gp/css/order-history','orders'],['/ap/signin','auth'],['/ap/cvf/verify','auth'],
  ['/errors/validateCaptcha','auth'],['/','other']]) {
  let message;vm.runInNewContext(fs.readFileSync('extensions/amazon-sync/ready.js','utf8'),{location:{pathname},chrome:{runtime:{sendMessage:msg=>{message=msg;return Promise.resolve();}}}});
  assert.equal(message?.page,expected==='orders'?undefined:expected);
 }
 result=await listeners.message({action:'sync',start:'2026-10-01',end:'2026-10-27'},popup);assert.equal(result.success,true);
 browser.tabs.get=async id=>({id,url:'https://example.com/'});
 result=await listeners.message({action:'sidecarOrders',orders:[]},english);assert.equal(result.success,true);assert.deepEqual(closed,[1]);
 await listeners.startup();console.log('Amazon extension scheduling, scoped submission and retry checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
