const $=id=>document.getElementById(id);
const saved=await chrome.storage.local.get(['settings','status']);
for(const key of ['url','token','account'])$(key).value=saved.settings?.[key]||(key==='account'?'default':'');
$('daily').checked=Boolean(saved.settings?.daily);$('status').textContent=saved.status||'Save the connection, then sync.';
const now=new Date();$('end').value=now.toISOString().slice(0,10);now.setDate(now.getDate()-90);$('start').value=now.toISOString().slice(0,10);
async function run(fn){try{await fn();}catch(e){$('status').textContent=e.message;}}
$('save').onclick=()=>run(async()=>{
 const url=new URL($('url').value);if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw Error('Use a plain http(s) sidecar URL, including its subpath.');
 if($('token').value.length<32)throw Error('Use a sync token of at least 32 characters.');
 if(!/^[A-Za-z0-9_-]{1,64}$/.test($('account').value))throw Error('Use a simple account label.');
 if(!await chrome.permissions.request({origins:[url.origin+'/*']}))throw Error('Sidecar access was not granted.');
 await chrome.storage.local.set({settings:{url:url.href.replace(/\/$/,''),token:$('token').value,account:$('account').value,daily:$('daily').checked}});
 await chrome.runtime.sendMessage({action:'configure'});$('status').textContent='Saved. Sign in to Amazon.es before syncing.';
});
for(const [id,action] of [['sync','sync'],['retry','retry'],['stop','stop']])$(id).onclick=()=>run(async()=>{const result=await chrome.runtime.sendMessage({action,start:$('start').value,end:$('end').value});if(!result.success)throw Error(result.error);$('status').textContent='Request accepted. You can close this popup.';});
chrome.storage.onChanged.addListener(changes=>{if(changes.status)$('status').textContent=changes.status.newValue;});
