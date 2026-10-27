// Requires npm ci --ignore-scripts in extensions/amazon-sync (same as its build).
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {build}=require('../extensions/amazon-sync/node_modules/esbuild');
(async()=>{
 const result=await build({entryPoints:['extensions/amazon-sync/vendor/src/content/content.ts'],bundle:true,write:false,format:'iife',plugins:[{
  name:'collector-harness',setup(plugin){
   plugin.onResolve({filter:/^webextension-polyfill$/},()=>({path:'browser',namespace:'harness'}));
   plugin.onLoad({filter:/.*/,namespace:'harness'},()=>({contents:'export default globalThis.testBrowser;'}));
   plugin.onLoad({filter:/content\.ts$/},args=>({loader:'ts',resolveDir:path.dirname(args.path),contents:fs.readFileSync(args.path,'utf8').replace('  function calculateProgress(', '  globalThis.collectorHarness = {finishExport, getExportState};\n  function calculateProgress(')}));
  }
 }]});
 const upstream=JSON.stringify({inProgress:true,collectedOrders:[{orderId:'upstream-order'}]});
 const storage=new Map([['amazonExporter',upstream]]),reads=[],messages=[],timers=[];let accept=true;
 const context=vm.createContext({console:{log(){},debug(){},warn(){}},document:{readyState:'complete'},setTimeout:fn=>timers.push(fn),
  sessionStorage:{getItem:key=>{reads.push(key);return storage.get(key)||null;},setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
  testBrowser:{i18n:{getMessage:key=>key},storage:{session:{get:async()=>({})}},runtime:{onMessage:{addListener(){}},sendMessage:async message=>{messages.push(message);return {success:accept,error:accept?undefined:'Import failed'};}}}
 });
 vm.runInContext(result.outputFiles[0].text,context);
 await timers.shift()(); // An unrelated upstream export must not be resumed.
 assert.equal(reads.includes('amazonExporter'),false);assert.equal(storage.get('amazonExporter'),upstream);
 const key='fireflySidecarAmazonSync.v1';
 const state={inProgress:true,includeTransactions:true,downloadInvoices:false,collectedOrders:[{orderId:'123-1234567-1234567',orderDate:'2026-10-20',currency:'EUR',totalAmount:30,chargedAmount:30,giftCardAmount:12.34,items:[{title:'Coffee',quantity:1}],detailsUrl:'',recipientStreet:'Private address'}]};
 storage.set(key,JSON.stringify(state));accept=false;
 await context.collectorHarness.finishExport(state);assert.ok(storage.has(key));
 accept=true;await context.collectorHarness.finishExport(state);
 assert.equal(storage.has(key),false);assert.equal(storage.get('amazonExporter'),upstream);
 const submitted=messages.filter(m=>m.action==='sidecarOrders');assert.equal(submitted.length,2);assert.equal(submitted[1].orders[0].orderId,state.collectedOrders[0].orderId);
 assert.equal(submitted[1].orders[0].giftCardAmount,12.34);assert.equal(submitted[1].orders[0].chargedAmount,30);
 assert.equal('recipientStreet' in submitted[1].orders[0],false);
 assert.equal(messages.some(m=>/download/i.test(m.action)),false);
 console.log('Collector coexistence, direct submission, address exclusion and failed-submission retention passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
