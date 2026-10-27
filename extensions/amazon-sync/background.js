import browser from 'webextension-polyfill';
const status=message=>browser.storage.local.set({status:message});
async function settings(){const {settings:s}=await browser.storage.local.get('settings');if(!s?.url||!s?.token)throw Error('Save the sidecar connection first.');return s;}
async function sendPending(){
 const {pending}=await browser.storage.local.get('pending');if(!pending)throw Error('No collected orders waiting to send.');const s=await settings();
 if(s.url!==pending.url||s.account!==pending.account)throw Error('Restore the original connection/account to retry, or run a new sync.');
 for(let i=0;i<pending.orders.length;i+=25){const response=await fetch(s.url+'/api/amazon/import',{method:'POST',redirect:'error',credentials:'omit',headers:{'Content-Type':'application/json','Authorization':'Bearer '+s.token},body:JSON.stringify({account:pending.account,marketplace:'amazon.es',orders:pending.orders.slice(i,i+25)})});if(!response.ok)throw Error('Sidecar import failed (HTTP '+response.status+'). Check URL, host and token, then Retry.');}
 await browser.storage.local.remove(['pending','job']);await status('Synced '+pending.orders.length+' orders. Review matches in Sidecar → Amazon Sync.');
}
async function begin(start,end){
 const s=await settings();const {pending}=await browser.storage.local.get('pending');if(pending)throw Error('Retry sending the collected orders before starting another sync.');const {job}=await browser.storage.local.get('job');if(job&&Date.now()-job.created<7200000)throw Error('A sync is already running. Stop it first.');
 if(!/^\d{4}-\d{2}-\d{2}$/.test(start)||!/^\d{4}-\d{2}-\d{2}$/.test(end)||start>end)throw Error('Choose a valid date range.');
 await browser.storage.session.setAccessLevel({accessLevel:'TRUSTED_AND_UNTRUSTED_CONTEXTS'});
 const tab=await browser.tabs.create({url:'about:blank',active:false});
 await browser.storage.local.set({job:{tabId:tab.id,created:Date.now(),start,end,started:false,url:s.url,account:s.account}});await browser.tabs.update(tab.id,{url:'https://www.amazon.es/gp/your-account/order-history'});await status('Opening Amazon.es. If prompted, sign in and start Sync now again.');
}
browser.tabs.onUpdated.addListener(async(tabId,change,tab)=>{
 if(change.status!=='complete'||tab.url==='about:blank')return;const {job}=await browser.storage.local.get('job');if(!job||job.tabId!==tabId||job.started)return;
 if(!tab.url?.startsWith('https://www.amazon.es/')||!(/order-history|your-orders/.test(tab.url))){await browser.storage.local.remove('job');await status('Complete Amazon sign-in or verification, then click Sync now.');return;}
 try{await browser.storage.local.set({job:{...job,started:true}});await browser.tabs.sendMessage(tabId,{action:'exportOrders',options:{format:'json',startDate:job.start,endDate:job.end,exportAll:false,includeTransactions:true,downloadInvoices:false}});await status('Collecting Amazon orders…');}catch{await browser.storage.local.remove('job');await status('Could not start collector. Reload Amazon orders and try again.');}
});
browser.tabs.onRemoved.addListener(async tabId=>{const {job}=await browser.storage.local.get('job');if(job?.tabId===tabId){await browser.storage.local.remove('job');await status('Sync tab closed. Unsent collected orders can be retried.');}});
browser.alarms.onAlarm.addListener(async alarm=>{if(alarm.name!=='amazon-daily')return;try{const s=await settings();if(!s.daily)return;const end=new Date(),start=new Date();start.setDate(start.getDate()-90);await begin(start.toISOString().slice(0,10),end.toISOString().slice(0,10));}catch(e){await status(e.message);}});
browser.runtime.onMessage.addListener((message,sender)=>{
 const internal=!sender.tab&&sender.id===browser.runtime.id;
 const collect=message.action==='sidecarOrders'&&sender.tab?.url?.startsWith('https://www.amazon.es/');
 if(message.action==='updateProgress'&&sender.tab?.url?.startsWith('https://www.amazon.es/'))return status(message.data?.message||'Collecting orders…').then(()=>({success:true}));
 if(!internal&&!collect)return;
 return (async()=>{
  if(collect){const {job}=await browser.storage.local.get('job');if(job?.tabId!==sender.tab.id)throw Error('No active sync for this tab.');const s=await settings();if(s.url!==job.url||s.account!==job.account)throw Error('Connection changed during collection. Restore the connection before retrying.');await browser.storage.local.set({pending:{url:s.url,account:s.account,orders:message.orders}});await sendPending();}
  else if(message.action==='sync')await begin(message.start,message.end);
  else if(message.action==='retry')await sendPending();
  else if(message.action==='configure'){await browser.alarms.clear('amazon-daily');const s=await settings();if(s.daily)await browser.alarms.create('amazon-daily',{periodInMinutes:1440});}
  else if(message.action==='stop'){const {job}=await browser.storage.local.get('job');if(job){try{await browser.tabs.sendMessage(job.tabId,{action:'stopExport'});}catch{}await browser.storage.local.remove('job');}await status('Sync stopped.');}
  return {success:true};
 })().catch(async e=>{await status(e.message);return {success:false,error:e.message};});
});

// Chrome may discard alarms across a browser restart.
browser.runtime.onStartup.addListener(async()=>{
 const {settings:s}=await browser.storage.local.get('settings');
 if(s?.daily)await browser.alarms.create('amazon-daily',{periodInMinutes:1440});
});
