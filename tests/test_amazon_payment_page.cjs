const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
for(const file of ['extensions/amazon-sync/vendor/src/content/content.ts','sidecar/amazon-extension/content.js']){
 const source=fs.readFileSync(file,'utf8'),start=source.indexOf('              const txResponse = await fetch(txUrl'),caught=source.indexOf('            } catch (txError)',start),end=source.indexOf('\n            }',caught+20)+'\n            }'.length;
 const run='(async()=>{try{\n'+source.slice(start,end)+'\n})()';
 async function check({rows=[],ok=true,status=200,url='https://www.amazon.es/cpe/yourpayments/transactions',login=false,fail=false}={}){
  const messages={warn:[],info:[],log:[]},existing=[{date:'2026-10-10',amount:10}],order={orderId:'123-1234567-1234567',transactions:existing,chargedAmount:10,giftCardAmount:0};
  const ctx=vm.createContext({order,txUrl:url,transactionHost:'www.amazon.es',fetch:async()=>{if(fail)throw Error('Network unavailable');return {ok,status,url,text:async()=>'<html/>'}},DOMParser:class{parseFromString(){return {querySelector:()=>login?{}:null}}},parseTransactionsFromCPEDoc:()=>rows,console:Object.fromEntries(Object.keys(messages).map(level=>[level,(...args)=>messages[level].push(args)]))});
  await vm.runInContext(run,ctx);return {messages,order,existing};
 }
 let result=await check();assert.equal(result.order.transactions,result.existing);assert.equal(result.messages.warn.length,0);assert.equal(result.messages.info.length,1);assert.equal(result.order.chargedAmount,10);
 const rows=[{date:'2026-10-11',amount:10}];result=await check({rows});assert.equal(result.order.transactions,rows);assert.equal(result.messages.warn.length,0);
 for(const options of [{ok:false,status:503},{login:true},{url:'https://www.amazon.es/ap/signin'},{fail:true}]){result=await check(options);assert.equal(result.messages.warn.length,1);assert.equal(result.order.transactions,result.existing)}
}
for(const file of ['extensions/amazon-sync/manifest.json','sidecar/amazon-extension/manifest.json'])assert.equal(JSON.parse(fs.readFileSync(file)).version,'0.1.8');
console.log('Optional payment-page empty results, retained data, successful parsing, HTTP/auth/network warnings and version parity passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
