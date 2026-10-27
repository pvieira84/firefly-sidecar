import browser from 'webextension-polyfill';
function amazonSpainUrl(value) {
 try {const url=new URL(value);return url.protocol==='https:'&&['amazon.es','www.amazon.es'].includes(url.hostname)&&!url.port;}catch{return false;}
}
const status=message=>browser.storage.local.set({status:message});
async function settings(){const {settings:s}=await browser.storage.local.get('settings');if(!s?.url||!s?.token)throw Error('Save the sidecar connection first.');return s;}
let sending = false;
async function sendPending(){
 if(sending)throw Error('Collected orders are already being sent. Wait for the result.');
 const {pending}=await browser.storage.local.get('pending');
 if(!pending)throw Error('No collected orders waiting to send.');
 const s=await settings();
 if(s.url!==pending.url||s.account!==pending.account)throw Error('Connection/account differs from the saved collection. Restore it to retry, or discard the collected orders before starting fresh.');
 sending=true;
 try {
  for(let i=0;i<pending.orders.length;i+=25){
   await status('Sending orders '+(i+1)+'–'+Math.min(i+25,pending.orders.length)+' of '+pending.orders.length+' to Sidecar…');
   let response;
   try {
    response=await fetch(s.url+'/api/amazon/import',{method:'POST',redirect:'error',credentials:'omit',headers:{'Content-Type':'application/json','Authorization':'Bearer '+s.token},body:JSON.stringify({account:pending.account,marketplace:'amazon.es',orders:pending.orders.slice(i,i+25)})});
   }catch {
    throw Error('Could not reach the Sidecar import endpoint. Check its URL, Chrome site permission and any proxy redirects. Collected orders are saved; use Retry sending collected orders.');
   }
   if(!response.ok){
    let detail='';
    try {const body=await response.json();if(typeof body.error==='string')detail=body.error.replaceAll(s.token,'[redacted]').slice(0,500);}catch{}
    throw Error('Sidecar import failed (HTTP '+response.status+'). '+(detail?detail+' ':'')+'Collected orders are saved; correct the connection or data issue, then Retry sending collected orders.');
   }
  }
  await browser.storage.local.remove(['pending','job']);
  await status('Synced '+pending.orders.length+' orders. Review matches in Sidecar → Amazon Sync.');
 }catch(error){
  await browser.storage.local.set({pending:{...pending,lastError:error.message}});
  throw error;
 }finally{sending=false;}
}
async function stopCollection(){
 const {job}=await browser.storage.local.get('job');
 if(job){try{await browser.tabs.sendMessage(job.tabId,{action:'stopExport'});}catch{}await browser.storage.local.remove('job');}
}
async function discardPending(){
 if(sending)throw Error('Orders are currently being sent. Wait for the result before discarding them.');
 await stopCollection();
 await browser.storage.local.remove('pending');
 await status('Collected orders discarded from this browser. Click Sync now to start fresh. Orders already imported into Sidecar are kept.');
}
async function begin(start,end){
 const s=await settings();const {pending}=await browser.storage.local.get('pending');if(pending)throw Error((pending.lastError?pending.lastError+' ':'')+'A saved collection is waiting. Use Retry sending collected orders, or Discard collected orders to start fresh.');const {job}=await browser.storage.local.get('job');if(job&&Date.now()-job.created<7200000)throw Error('A sync is already running. Stop it first.');
 if(!/^\d{4}-\d{2}-\d{2}$/.test(start)||!/^\d{4}-\d{2}-\d{2}$/.test(end)||start>end)throw Error('Choose a valid date range.');
 await browser.storage.session.setAccessLevel({accessLevel:'TRUSTED_AND_UNTRUSTED_CONTEXTS'});
 const tab=await browser.tabs.create({url:'about:blank',active:false});
 await browser.storage.local.set({job:{tabId:tab.id,created:Date.now(),start,end,started:false,url:s.url,account:s.account}});await status('Opening Amazon.es; waiting for the order collector…');await browser.tabs.update(tab.id,{url:'https://www.amazon.es/gp/your-account/order-history'});
}
// Tab update events can omit tab.url or describe an intermediate redirect.
// Start only when the document's content script confirms it is ready.
async function collectorReady(sender, page) {
 const {job}=await browser.storage.local.get('job');
 if(!job||job.tabId!==sender.tab.id)return {success:false};
 if(page==='auth') {
  await status('Amazon is showing sign-in or verification. Complete it in the sync tab; collection will continue when you return to orders.');
  return {success:true};
 }
 if(page!=='orders') {
  if(!job.started)await status('Waiting for the Amazon orders page. Open Your Orders in the sync tab.');
  return {success:true};
 }
 if(job.started)return {success:true};
 await browser.storage.local.set({job:{...job,started:true}});
 try {
  const response=await browser.tabs.sendMessage(sender.tab.id,{action:'exportOrders',options:{format:'json',startDate:job.start,endDate:job.end,exportAll:false,includeTransactions:true,downloadInvoices:false}});
  if(!response?.success)throw Error('Collector did not acknowledge start.');
  await status('Collecting Amazon orders…');
  return {success:true};
 }catch {
  await browser.storage.local.set({job:{...job,started:false}});
  await status('The orders page loaded, but the collector is unavailable. Reload this Amazon tab after reloading the extension.');
  return {success:false};
 }
}
browser.tabs.onRemoved.addListener(async tabId=>{const {job}=await browser.storage.local.get('job');if(job?.tabId===tabId){await browser.storage.local.remove('job');await status('Sync tab closed. Unsent collected orders can be retried.');}});
browser.alarms.onAlarm.addListener(async alarm=>{if(alarm.name!=='amazon-daily')return;try{const s=await settings();if(!s.daily)return;const end=new Date(),start=new Date();start.setDate(start.getDate()-90);await begin(start.toISOString().slice(0,10),end.toISOString().slice(0,10));}catch(e){await status(e.message);}});
browser.runtime.onMessage.addListener((message,sender)=>{
 const internal=!sender.tab&&sender.id===browser.runtime.id;
 const amazon=Boolean(sender.tab)&&amazonSpainUrl(sender.url||sender.tab.url);
 if(message.action==='collectorReady'&&amazon)return collectorReady(sender,message.page);
 const collect=message.action==='sidecarOrders'&&amazon;
 if(message.action==='updateProgress'&&amazon)return status(message.data?.message||'Collecting orders…').then(()=>({success:true}));
 if(!internal&&!collect)return;
 return (async()=>{
  if(collect){const {job}=await browser.storage.local.get('job');if(job?.tabId!==sender.tab.id)throw Error('No active sync for this tab.');const s=await settings();if(s.url!==job.url||s.account!==job.account)throw Error('Connection changed during collection. Restore the connection before retrying.');await browser.storage.local.set({pending:{url:s.url,account:s.account,orders:message.orders}});await sendPending();}
  else if(message.action==='sync')await begin(message.start,message.end);
  else if(message.action==='retry')await sendPending();
  else if(message.action==='discard')await discardPending();
  else if(message.action==='configure'){await browser.alarms.clear('amazon-daily');const s=await settings();if(s.daily)await browser.alarms.create('amazon-daily',{periodInMinutes:1440});}
  else if(message.action==='stop'){
   await stopCollection();const {pending}=await browser.storage.local.get('pending');
   await status(sending?'Collection stopped; the current Sidecar upload is still finishing.':pending?'Collection stopped. Collected orders are kept. Choose Retry sending collected orders or Discard collected orders before starting fresh.':'Sync stopped.');
  }
  return {success:true};
 })().catch(async e=>{await status(e.message);return {success:false,error:e.message};});
});

// Chrome may discard alarms across a browser restart.
browser.runtime.onStartup.addListener(async()=>{
 const {settings:s}=await browser.storage.local.get('settings');
 if(s?.daily)await browser.alarms.create('amazon-daily',{periodInMinutes:1440});
});
