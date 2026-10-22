'use strict';
const $ = id => document.getElementById(id);
let config, data = {deposits: [], expenses: []}, selected = new Set(), plan, busy = false, loaded = false;
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value, currency) => { try { return new Intl.NumberFormat(undefined, {style:'currency',currency}).format(value); } catch { return `${value} ${currency}`; } };
const date = s => String(s || '').slice(0,10);
// Exact decimal arithmetic (Firefly supports up to 12 decimal places).
function units(value) {
  const match = /^(\d+)(?:\.(\d{1,12}))?$/.exec(String(value));
  if (!match) throw new Error('Unsupported amount format. Refresh or inspect this transaction in Firefly.');
  return BigInt(match[1]) * 1000000000000n + BigInt((match[2] || '').padEnd(12,'0'));
}
function decimal(value) { const sign=value<0n?'-':''; const s=(value<0n?-value:value).toString().padStart(13,'0'); return sign+s.slice(0,-12)+'.'+s.slice(-12); }
function differenceWarning(depositAmount, total, currency) {
  const remaining=units(depositAmount)-units(total);
  if(remaining===0n) return '';
  return `Selected reimbursements are ${fmt(decimal(remaining<0n?-remaining:remaining),currency)} ${remaining<0n?'more':'less'} than the deposit. You can continue; the pending tag will be removed from every selected split.`;
}
function notice(message, success=false) { $('message').textContent=message; $('message').className=success?'success':''; $('message').hidden=false; }
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Sidecar-CSRF':config.csrf},body:JSON.stringify(body)});
  const json = await r.json();
  if (!r.ok) throw new Error(json.error || 'Request failed.');
  return json;
}
function currentDeposit() { return data.deposits.find(x => x.journal_id === $('deposit').value); }
function selection() { return data.expenses.filter(x => selected.has(x.journal_id)); }
function setBusy(value) {
  busy=value;
  for(const id of ['filter-dates','review','apply','test-connection','cancel-review','load-validation','load-duplicates','cancel-delete','confirm-delete','more-activity']) $(id).disabled=value;
  $('deposit').disabled=value || !loaded;
  renderExpenses();
  renderValidation();
}
async function perform(fn) {
  if(busy) return;
  setBusy(true);
  try { await fn(); } catch(e) { if($('review-dialog').open) $('review-dialog').close(); notice(e.message); } finally { setBusy(false); }
}
function renderStats() {
  $('pending-count').textContent=data.expenses.length;
  const totals = new Map();
  for(const x of data.expenses) totals.set(x.currency_code,(totals.get(x.currency_code)||0n)+units(x.amount));
  $('outstanding').textContent=Array.from(totals,([c,n])=>fmt(decimal(n),c)).join(' · ') || '—';
  $('tag-label').textContent=config.tag.startsWith('#')?config.tag:'#'+config.tag;
}
function renderBalance() {
  const d=currentDeposit(), items=selection();
  const totals=new Map();
  for(const x of items) totals.set(x.currency_code,(totals.get(x.currency_code)||0n)+units(x.amount));
  $('selected-total').textContent=Array.from(totals,([c,n])=>fmt(decimal(n),c)).join(' · ') || '—';
  $('selection-count').textContent=items.length?`${items.length} reimbursement split${items.length===1?'':'s'} selected`:'Choose expenses below';
  let valid=false;
  if(!d) {
    $('balance-label').textContent='Choose a deposit and expenses';
    $('balance-help').textContent='Choose at least one reimbursement in the deposit currency. Totals may differ.';
    $('deposit-detail').textContent='Choose an incoming payment to start matching.';
  } else {
    const total=totals.get(d.currency_code)||0n, remaining=units(d.amount)-total;
    valid=items.length>0 && items.length<=100 && totals.size===1 && totals.has(d.currency_code);
    $('deposit-detail').innerHTML=`${esc(date(d.date))} · ${esc(d.source_name)} → ${esc(d.destination_name)} · Journal #${esc(d.journal_id)} · ${fireflyLink(d.group_id,'Open in Firefly')}`;
    $('balance-label').textContent=remaining===0n?'Exact match — ready to review':remaining<0n?'Selection exceeds the deposit':`${fmt(decimal(remaining),d.currency_code)} left to match`;
    $('balance-help').textContent=items.length?(differenceWarning(d.amount,decimal(total),d.currency_code)||'Each selected split will be linked to this deposit.'):'Choose at least one reimbursement to review.';
  }
  $('review').disabled=busy || !valid;
}
function renderExpenses() {
  const d=currentDeposit(), q=$('search').value.toLowerCase();
  const rows=data.expenses.filter(x=>[x.group_title,x.description,x.destination_name,x.source_name,x.amount,x.journal_id,...(x.tags||[])].join(' ').toLowerCase().includes(q));
  $('expenses').innerHTML=rows.map(x=>{
    const disabled=!!d && x.currency_code!==d.currency_code;
    return `<tr class="${selected.has(x.journal_id)?'selected ':''}${disabled?'unavailable':''}"><td><input type="checkbox" aria-label="Select ${esc(x.group_title||x.destination_name)} reimbursement ${esc(x.journal_id)}" data-journal="${esc(x.journal_id)}" ${selected.has(x.journal_id)?'checked':''} ${disabled||busy?'disabled':''}></td><td><strong>${fireflyLink(x.group_id,x.group_title||x.destination_name||x.description)}</strong><small>${esc(x.description)} · ${esc(x.destination_name)} · Split #${esc(x.journal_id)}</small></td><td><div class="row-tags">${(x.tags||[]).map(tag=>`<span class="tag">${esc(tag.startsWith('#')?tag:'#'+tag)}</span>`).join('') || '—'}</div></td><td>${esc(date(x.date))}</td><td>${esc(x.source_name)}</td><td class="right"><strong>${esc(fmt(x.amount,x.currency_code))}</strong>${disabled?'<small>Different currency</small>':''}</td></tr>`;
  }).join('')||'<tr><td colspan="6" class="empty">'+(!loaded?'Set the deposit date range, then click Load from Firefly.':data.expenses.length?'No expenses match your search.':'No pending reimbursement splits. You’re all caught up.')+'</td></tr>';
  $('visible-count').textContent=`${rows.length} of ${data.expenses.length} pending splits`;
  renderBalance();
}
async function load() {
  if (!$('start').value || !$('end').value) throw new Error('Choose both deposit dates before loading.');
  if ($('start').value > $('end').value) throw new Error('The start date must be on or before the end date.');
  notice('Loading deposits and outstanding reimbursements from Firefly…');
  const query=new URLSearchParams({start:$('start').value,end:$('end').value});
  const old=$('deposit').value;
  data=await api('/api/reimbursements?'+query);
  loaded=true;
  notice('Transactions loaded.',true);
  selected=new Set([...selected].filter(id=>data.expenses.some(x=>x.journal_id===id)));
  $('deposit').innerHTML='<option value="">Select a deposit…</option>'+data.deposits.map(x=>`<option value="${esc(x.journal_id)}">${esc(date(x.date))} · ${esc(x.description)} · ${esc(fmt(x.amount,x.currency_code))} · #${esc(x.journal_id)}</option>`).join('');
  if(data.deposits.some(x=>x.journal_id===old)) $('deposit').value=old;
  renderStats(); renderExpenses();
}
function renderPlan(p) {
  plan=p;
  const d=p.deposit;
  $('review-content').innerHTML=`<div class="review-deposit"><strong>${fireflyLink(d.group_id,d.description)}</strong><p>${esc(date(d.date))} · ${esc(d.source_name)} · Deposit #${esc(d.transaction_journal_id)}</p><strong>${esc(fmt(d.amount,p.currency))}</strong></div>`+p.expenses.map(x=>`<div class="review-line"><div>${fireflyLink(x.group_id,x.group_title||x.destination_name)}<br><small>Reimbursement split #${esc(x.journal_id)}</small></div><strong>${esc(fmt(x.amount,x.currency_code))}</strong></div>`).join('')+`<div class="review-line review-total"><span>Selected reimbursement total</span><span>${esc(fmt(p.total,p.currency))}</span></div>${differenceWarning(d.amount,p.total,p.currency)?`<p class="match-warning" role="status">${esc(differenceWarning(d.amount,p.total,p.currency))}</p>`:''}<p class="review-note">Expense split <b>${esc(p.link_type.inward)}</b> deposit.<br>Each verified link is followed by removal of the <b>${esc(p.tag)}</b> tag from that expense split. Other tags are preserved.</p>`;
  $('review-dialog').showModal();
}
async function applyPlan(id) {
  const r=await api('/api/reimbursements/apply',{plan_id:id});
  if($('review-dialog').open) $('review-dialog').close();
  if(r.complete) { notice(`Reimbursement complete. ${r.items.length} split${r.items.length===1?'':'s'} linked and pending tags removed.`,true); selected.clear(); }
  else { notice('Operation paused. Some changes may have completed. Open Activity to inspect the result and retry.\n'+r.items.filter(x=>x.error).map(x=>`Split #${x.journal_id}: ${x.error}`).join('\n')); }
  const completed=new Set(r.items.filter(x=>x.status==='complete').map(x=>x.journal_id));
  data.expenses=data.expenses.filter(x=>!completed.has(x.journal_id));
  for(const id of completed) selected.delete(id);
  if(r.complete) {
    data.deposits=data.deposits.filter(x=>x.journal_id!==String(plan.deposit.transaction_journal_id));
    for(const option of [...$('deposit').options]) if(option.value===String(plan.deposit.transaction_journal_id)) option.remove();
    $('deposit').value='';
  }
  renderStats(); renderExpenses();
  await loadHistory();
}
async function loadHistory() {
  await loadActivity();
  const rows=await api('/api/history');
  $('history-list').innerHTML=rows.map(x=>`<article class="card history-card"><div class="history-heading"><strong>${fireflyLink(x.plan.deposit.group_id,x.plan.deposit.description)} · ${esc(fmt(x.plan.total,x.plan.currency))}</strong><span class="status">${esc(x.state)}</span></div><p>${esc(x.created.slice(0,19).replace('T',' '))} UTC · ${x.plan.expenses.length} splits · Deposit #${esc(x.plan.deposit.transaction_journal_id)}</p><p>${x.plan.expenses.map(e=>fireflyLink(e.group_id,'Split #'+e.journal_id)).join(' · ')}</p><ul>${(x.result?.items||[]).map(i=>`<li>Split #${esc(i.journal_id)}: ${esc(i.status)}${i.error?' — '+esc(i.error):''}</li>`).join('')}</ul>${x.state!=='complete'?`<button class="secondary" data-resume="${esc(x.id)}">${x.state==='review'?'Open review':'Inspect & resume'}</button>`:''}</article>`).join('')||'<div class="card empty">Your reimbursement activity will appear here.</div>';
  $('history-list').querySelectorAll('[data-resume]').forEach(button=>button.addEventListener('click',()=>perform(async()=>renderPlan(rows.find(x=>x.id===button.dataset.resume).plan))));
}
const autoLoadedTools=new Set();
async function view(name) {
  document.querySelectorAll('.view').forEach(x=>x.hidden=x.id!==name);
  document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.view===name));
  $('breadcrumb').textContent={validation:'Transaction review',reimbursements:'Reimbursements',duplicates:'Duplicate checker',history:'Activity',connection:'Connection'}[name];
  if(config?.configured && ['validation','reimbursements','duplicates'].includes(name) && !autoLoadedTools.has(name)) {
    autoLoadedTools.add(name);
    if(name==='validation') await loadValidation();
    else if(name==='duplicates') await loadDuplicates();
    else await load();
  }
  if(name==='history') await loadHistory();
}
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>perform(()=>view(button.dataset.view))));
$('filter-dates').addEventListener('click',()=>perform(load));
$('deposit').addEventListener('change',()=>{selected.clear();renderExpenses();});
$('search').addEventListener('input',renderExpenses);
$('expenses').addEventListener('change',e=>{const id=e.target.dataset.journal;if(!id||busy)return;e.target.checked?selected.add(id):selected.delete(id);renderExpenses();});
$('clear').addEventListener('click',()=>{if(!busy){selected.clear();renderExpenses();}});
$('review').addEventListener('click',()=>perform(async()=>renderPlan(await api('/api/reimbursements/review',{deposit_id:$('deposit').value,expense_ids:[...selected]}))));
$('cancel-review').addEventListener('click',()=>$('review-dialog').close());
$('review-dialog').addEventListener('cancel',e=>{if(busy)e.preventDefault();});
$('apply').addEventListener('click',()=>perform(()=>applyPlan(plan.id)));
$('test-connection').addEventListener('click',()=>perform(async()=>{const r=await api('/api/connection');$('connection-state').textContent=`Connected · Firefly III ${r.version}`;notice('Firefly III connection verified.',true);}));
(async()=>{
  const today=new Date(), start=new Date(today);
  start.setDate(start.getDate()-7);
  const localDate=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  $('start').value=localDate(start);
  $('end').value=localDate(today);
  $('duplicates-start').value=localDate(start);
  $('duplicates-end').value=localDate(today);
  try {
    config=await api('/api/bootstrap');
    $('connection-url').textContent=config.firefly_public_url||'Set FIREFLY_PUBLIC_URL to enable Open in Firefly links.';
    $('connection-state').textContent=config.configured?'Credentials configured on server. Test the connection below.':'Configuration required.';
    $('matching-rules').textContent=`Pending tag: ${config.tag}. All uncategorized withdrawals carrying this tag are included, regardless of description. Change the tag using REIMBURSE_TAG.`;
    if(!config.configured){await view('connection');notice('Add your Firefly III URL and API token to the Docker environment to get started.');return;}
    $('todo-tag').textContent=config.todo_tag;
    renderStats(); renderExpenses();
    await perform(()=>view('validation'));
  } catch(e) { notice(e.message); }
})();

let validationRows=[], validationLoaded=false;
function renderValidation() {
  const q=$('validation-search').value.toLowerCase();
  const rows=validationRows.filter(x=>[x.group_title,x.description,x.source_name,x.destination_name,x.category_name,...(x.tags||[])].join(' ').toLowerCase().includes(q));
  $('validation-rows').innerHTML=rows.map(x=>`<tr><td><strong>${fireflyLink(x.group_id,x.description)}</strong><small>${esc(x.group_title)} · Journal #${esc(x.journal_id)}</small></td><td>${esc(date(x.date))}</td><td>${esc(x.source_name)} → ${esc(x.destination_name)}</td><td>${esc(x.category_name||'Uncategorized')}</td><td><div class="row-tags">${(x.tags||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div></td><td class="right">${esc(fmt(x.amount,x.currency_code))}</td><td>${reviewDuplicateStatus(x.duplicate_check)}</td><td><button class="secondary" data-validate="${esc(x.journal_id)}" ${busy?'disabled':''}>Mark validated</button> ${deleteButton(x.group_id)}</td></tr>`).join('')||`<tr><td colspan="8" class="empty">${validationLoaded?'No transactions match.':'Click Load from Firefly to see transactions awaiting validation.'}</td></tr>`;
  $('validation-count').textContent=validationLoaded?`${rows.length} of ${validationRows.length} awaiting validation`:'Not loaded';
}
async function loadValidation() {
  notice('Loading review queue and checking nearby transactions for duplicates…');
  const result=await api('/api/validation');
  validationRows=result.transactions;validationLoaded=true;$('todo-tag').textContent=result.tag;
  renderValidation();notice('Review queue loaded.',true);
}
$('load-validation').addEventListener('click',()=>perform(loadValidation));
$('validation-search').addEventListener('input',renderValidation);
$('validation-rows').addEventListener('click',event=>{
  if(busy)return;
  const deletion=event.target.closest('[data-delete]');
  if(deletion){perform(()=>previewDelete(deletion.dataset.delete));return;}
  const button=event.target.closest('[data-validate]');if(!button)return;
  perform(async()=>{
    const jid=button.dataset.validate;
    await api('/api/validation/complete',{journal_id:jid});
    validationRows=validationRows.filter(x=>x.journal_id!==jid);
    renderValidation();notice('Transaction marked validated.',true);
  });
});

function fireflyLink(id, label) {
  try {
    if(!id) return esc(label);
    const base=new URL(config.firefly_public_url);
    if(!['http:','https:'].includes(base.protocol)) return esc(label);
    return `<a href="${esc(base.href.replace(/\/$/,'')+'/transactions/show/'+encodeURIComponent(id))}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  } catch {return esc(label);}
}
function duplicateCard(row, deletable=false) {
  return `<article class="duplicate-transaction"><h3>${fireflyLink(row.group_id,row.title)}</h3>${deletable?deleteButton(row.group_id):''}<p>${esc(row.date)} · ${esc(row.type)} · Transaction #${esc(row.group_id)}</p><strong>${esc(fmt(row.total,row.currency))}</strong><p>${row.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join(' ')||'No tags'}</p><details><summary>${row.splits.length} journal${row.splits.length===1?'':'s'} · Split breakdown</summary>${row.splits.map(s=>`<div class="review-line"><div>${esc(s.description)}<small> #${esc(s.journal_id)} · ${esc(s.source)} → ${esc(s.destination)}</small></div><strong>${esc(fmt(s.amount,row.currency))}</strong></div>`).join('')}</details></article>`;
}
async function loadDuplicates() {
  const start=$('duplicates-start').value,end=$('duplicates-end').value,days=$('duplicates-days').value;
  if(!start||!end||start>end) throw new Error('Choose a valid duplicate-check date range.');
  if(!/^\d+$/.test(days)||Number(days)>31) throw new Error('Days apart must be a whole number between 0 and 31.');
  notice('Checking transaction totals for duplicates…');
  const result=await api('/api/duplicates?'+new URLSearchParams({start,end,days}));
  $('duplicates-summary').textContent=`${result.scanned} transactions scanned · ${result.pairs.length} candidate pairs · ${result.skipped.length} needing manual review`;
  $('duplicates-results').innerHTML=result.pairs.map(pair=>`<section class="card duplicate-pair"><div class="duplicate-heading">Same total, currency, type and account · ${pair.days_apart} day${pair.days_apart===1?'':'s'} apart${pair.signals.length?' · '+esc(pair.signals.join(' · ')):''}</div><div class="duplicate-columns">${duplicateCard(pair.left)}${duplicateCard(pair.right)}</div></section>`).join('')||'<div class="card empty">No duplicate candidates found in this range.</div>';
  $('duplicates-skipped').hidden=!result.skipped.length;
  $('duplicates-skipped-list').innerHTML=result.skipped.map(row=>`<p>${fireflyLink(row.group_id,row.title)}: ${esc(row.reason)}</p>`).join('');
  notice(result.truncated?'Showing the first 500 candidate pairs. Narrow the date range to inspect more.':'Duplicate check complete. Candidates require manual review.',!result.truncated);
}
$('load-duplicates').addEventListener('click',()=>perform(loadDuplicates));

function reviewDuplicateStatus(check) {
  if(!check) return '<span class="muted">Not checked</span>';
  if(check.status!=='checked') return `<span class="duplicate-alert">${check.status==='manual'?'Manual review needed':'Check unavailable'}</span><small>${esc(check.reason)}</small>`;
  if(!check.match_count) return `<span class="muted">No candidates within ±${check.days} days</span>`;
  return `<details class="review-duplicates"><summary class="duplicate-alert">${check.match_count} potential duplicate${check.match_count===1?'':'s'}</summary><p>Same parent total, currency, type and account. Review before validating.</p>${duplicateCard(check.source,true)}${check.matches.map(match=>`<div class="review-duplicate-match"><p>${match.days_apart} days apart${match.signals.length?' · '+esc(match.signals.join(' · ')):''}</p>${duplicateCard(match.transaction,true)}</div>`).join('')}${check.truncated?'<p>Showing the first 20 matches.</p>':''}</details>`;
}

let deletionPreview;
function deleteButton(groupId) {
  return `<button class="danger-small" data-delete="${esc(groupId)}" ${busy?'disabled':''}>Delete transaction</button>`;
}
async function previewDelete(groupId) {
  deletionPreview=await api('/api/validation/delete-preview',{group_id:groupId});
  const group=deletionPreview.transaction, splits=group.attributes.transactions;
  $('delete-content').innerHTML=`<h3>${fireflyLink(deletionPreview.group_id,group.attributes.group_title||splits[0]?.description||'Transaction')}</h3><p>Transaction #${esc(deletionPreview.group_id)} · ${splits.length} journal${splits.length===1?'':'s'} will be deleted.</p>`+splits.map(s=>`<div class="review-line"><div>${esc(s.description)}<small>#${esc(s.transaction_journal_id)} · ${esc(date(s.date))} · ${esc(s.source_name)} → ${esc(s.destination_name)}</small><p>${(s.tags||[]).map(esc).join(' · ')}</p></div><strong>${esc(fmt(s.amount,s.currency_code))}</strong></div>`).join('');
  $('delete-dialog').showModal();
}
$('cancel-delete').addEventListener('click',()=>{deletionPreview=undefined;$('delete-dialog').close();});
$('delete-dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault();else deletionPreview=undefined;});
$('confirm-delete').addEventListener('click',()=>perform(async()=>{
  if(!deletionPreview)throw new Error('Open a deletion preview first.');
  const result=await api('/api/validation/delete',{token:deletionPreview.token});
  deletionPreview=undefined;$('delete-dialog').close();
  const gid=result.group_id;
  validationRows=validationRows.filter(row=>row.group_id!==gid);
  data.expenses=data.expenses.filter(row=>row.group_id!==gid);
  data.deposits=data.deposits.filter(row=>row.group_id!==gid);
  for(const row of validationRows) {
    const check=row.duplicate_check;
    if(check?.status==='checked') {check.matches=check.matches.filter(m=>m.transaction.group_id!==gid);check.match_count=check.matches.length;}
  }
  autoLoadedTools.delete('duplicates');autoLoadedTools.delete('reimbursements');
  renderValidation();renderStats();renderExpenses();
  try {await loadValidation();notice(`Transaction #${gid} and all its splits were deleted.`,true);}
  catch(error){notice(`Transaction #${gid} was deleted. Reload the queue: ${error.message}`);}
}));

let activityEvents=[], activityOffset=null;
async function loadActivity(append=false) {
  const result=await api('/api/activity?offset='+(append?activityOffset:0));
  activityEvents=append?activityEvents.concat(result.events):result.events;
  activityOffset=result.next_offset;
  $('activity-list').innerHTML=activityEvents.map(event=>`<article class="card history-card"><div class="history-heading"><strong>${esc(event.action)}</strong><span class="status">${esc(event.state)}</span></div><p>${esc(event.created)} · ${esc(event.method)} ${esc(event.path)}</p>${event.group_id?`<p>${fireflyLink(event.group_id,'Transaction #'+event.group_id)}${event.method==='DELETE'?' (may no longer exist in Firefly)':''}</p>`:''}${(event.tag_changes||[]).map(change=>`<p>Journal #${esc(change.journal_id)}: ${esc(change.before.join(', ')||'No tags')} → ${esc(change.after.join(', ')||'No tags')}</p>`).join('')}${event.error?`<p class="duplicate-alert">${esc(event.error)}</p>`:''}${event.verification_note?`<p>${esc(event.verification_note)}</p>`:''}<details><summary>Request and transaction snapshots</summary><pre class="audit-json">${esc(JSON.stringify({request:event.request,before:event.before,after:event.after,response:event.response},null,2))}</pre></details></article>`).join('')||'<div class="card empty">No recorded Firefly changes yet.</div>';
  $('more-activity').hidden=activityOffset===null;
}
$('more-activity').addEventListener('click',()=>perform(()=>loadActivity(true)));
