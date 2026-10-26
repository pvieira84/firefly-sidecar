'use strict';
const $ = id => document.getElementById(id);
let config, data = {deposits: [], expenses: []}, selected = new Set(), plan, busy = false, loaded = false;
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value, currency) => { try { return new Intl.NumberFormat(undefined, {style:'currency',currency}).format(value); } catch { return `${value} ${currency}`; } };
const date = s => String(s || '').slice(0,10);
function activityTimestamp(value) {
  const timestamp=new Date(value);
  if(!value||Number.isNaN(timestamp.getTime()))return esc(value||'Unknown time');
  const display=new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'medium'}).format(timestamp);
  const zone=Intl.DateTimeFormat().resolvedOptions().timeZone;
  return `<time datetime="${esc(timestamp.toISOString())}" title="${esc(value)} · ${esc(zone)}">${esc(display)}</time>`;
}

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
  const r = await fetch((document.documentElement?.dataset?.basePath || '') + path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Sidecar-CSRF':config.csrf},body:JSON.stringify(body)});
  const json = await r.json();
  if (!r.ok) throw new Error(json.error || 'Request failed.');
  return json;
}
function currentDeposit() { return data.deposits.find(x => x.journal_id === $('deposit').value); }
function selection() { return data.expenses.filter(x => selected.has(x.journal_id)); }
function setBusy(value) {
  busy=value;
  for(const id of ['filter-dates','review','apply','test-connection','cancel-review','load-validation','load-duplicates','cancel-delete','confirm-delete','more-activity','previous-activity','apply-activity-filters','reset-activity-filters','activity-action','activity-state','activity-group','activity-start','activity-end','activity-limit','more-duplicates','load-refund','confirm-refund','cancel-refund','refund-start','refund-end','refund-tolerance','refund-remove-todo','refund-same-account','load-gbit','apply-gbit','cancel-gbit','gbit-new','gbit-original','gbit-refund','gbit-start','gbit-end','gbit-search','cancel-categorize','categorize-source','categorize-destination','categorize-category','categorize-budget','categorize-bill','reimbursement-mode','reimbursement-value','cancel-reimbursement']) $(id).disabled=value;
  $('deposit').disabled=value || !loaded;
  renderExpenses();
  renderValidation();
  renderDuplicatePairs();
  activityPageControls();
  renderGbitDetails();
  categorizeControls();
  reimbursementControls();
  refundSelectionControls();
  document.querySelectorAll('#refund-candidates input').forEach(input=>input.disabled=value);
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
    $('deposit-detail').innerHTML=`${esc(date(d.date))} · ${esc(d.source_name)} → ${esc(d.destination_name)} · ${esc(transactionIdLabel(d))} · ${fireflyLink(d.group_id,'Open in Firefly')}`;
    $('balance-label').textContent=remaining===0n?'Exact match — ready to review':remaining<0n?'Selection exceeds the deposit':`${fmt(decimal(remaining),d.currency_code)} left to match`;
    $('balance-help').textContent=items.length?(differenceWarning(d.amount,decimal(total),d.currency_code)||'Each selected split will be linked to this deposit.'):'Choose at least one reimbursement to review.';
  }
  $('review').disabled=busy || !valid;
}
function renderExpenses() {
  const d=currentDeposit(), q=$('search').value.toLowerCase();
  const rows=data.expenses.filter(x=>[x.group_title,x.description,x.destination_name,x.source_name,x.amount,x.journal_id,...(x.tags||[])].join(' ').toLowerCase().includes(q));
  const groups=new Map();
  for(const row of rows) {
    if(!groups.has(row.group_id))groups.set(row.group_id,[]);
    groups.get(row.group_id).push(row);
  }
  $('expenses').innerHTML=[...groups.values()].map(journals=>{
    const parent=journals[0];
    const heading=(parent.journal_count>1||journals.length>1)?`<tr class="validation-parent"><td></td><td colspan="5"><strong>${fireflyLink(parent.group_id,`#${parent.group_id} · ${parent.group_title||parent.description}`)}</strong><small>${journals.length} pending reimbursement split${journals.length===1?'':'s'}</small></td></tr>`:'';
    return heading+journals.map(x=>{
    const disabled=!!d && x.currency_code!==d.currency_code;
    return `<tr class="${selected.has(x.journal_id)?'selected ':''}${disabled?'unavailable':''}"><td><input type="checkbox" aria-label="Select ${esc(x.group_title||x.description||x.destination_name)} ${esc(transactionIdLabel(x))}" data-journal="${esc(x.journal_id)}" ${selected.has(x.journal_id)?'checked':''} ${disabled||busy?'disabled':''}></td><td><strong>${fireflyLink(x.group_id,x.group_title||x.description||x.destination_name)}</strong><small>${esc(x.description)} · ${esc(x.destination_name)} · ${esc(transactionIdLabel(x))}</small></td><td><div class="row-tags">${(x.tags||[]).map(tag=>`<span class="tag">${esc(tag.startsWith('#')?tag:'#'+tag)}</span>`).join('') || '—'}</div></td><td>${esc(date(x.date))}</td><td>${esc(x.source_name)}</td><td class="right"><strong>${esc(fmt(x.amount,x.currency_code))}</strong>${disabled?'<small>Different currency</small>':''}</td></tr>`;
    }).join('');
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
  $('deposit').innerHTML='<option value="">Select a deposit…</option>'+data.deposits.map(x=>`<option value="${esc(x.journal_id)}">${esc(date(x.date))} · ${esc(x.description)} · ${esc(fmt(x.amount,x.currency_code))} · ${esc(transactionIdLabel(x))}</option>`).join('');
  if(data.deposits.some(x=>x.journal_id===old)) $('deposit').value=old;
  renderStats(); renderExpenses();
}
function renderPlan(p) {
  plan=p;
  const d=p.deposit;
  $('review-content').innerHTML=`<div class="review-deposit"><strong>${fireflyLink(d.group_id,d.description)}</strong><p>${esc(date(d.date))} · ${esc(d.source_name)} · ${esc(transactionIdLabel(d))}</p><strong>${esc(fmt(d.amount,p.currency))}</strong></div>`+p.expenses.map(x=>`<div class="review-line"><div>${fireflyLink(x.group_id,x.group_title||x.description||x.destination_name)}<br><small>${esc(transactionIdLabel(x))}</small></div><strong>${esc(fmt(x.amount,x.currency_code))}</strong></div>`).join('')+`<div class="review-line review-total"><span>Selected reimbursement total</span><span>${esc(fmt(p.total,p.currency))}</span></div>${differenceWarning(d.amount,p.total,p.currency)?`<p class="match-warning" role="status">${esc(differenceWarning(d.amount,p.total,p.currency))}</p>`:''}<p class="review-note">Deposit <b>${esc(p.link_type.outward)}</b> expense split.<br>Each verified link is followed by removal of the <b>${esc(p.tag)}</b> tag from that expense split. Other tags are preserved.</p>`;
  $('review-dialog').showModal();
}
async function applyPlan(id) {
  const r=await api('/api/reimbursements/apply',{plan_id:id});
  if($('review-dialog').open) $('review-dialog').close();
  if(r.complete) { notice(`Reimbursement complete. ${r.items.length} split${r.items.length===1?'':'s'} linked and pending tags removed.`,true); selected.clear(); }
  else { notice('Operation paused. Some changes may have completed. Open Activity to inspect the result and retry.\n'+r.items.filter(x=>x.error).map(x=>`${transactionIdLabel(plan.expenses.find(row=>row.journal_id===x.journal_id)||x)}: ${x.error}`).join('\n')); }
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
async function loadHistory() {await loadActivity();}
const autoLoadedTools=new Set();
async function view(name) {
  document.querySelectorAll('.view').forEach(x=>x.hidden=x.id!==name);
  document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.view===name));
  $('breadcrumb').textContent={validation:'Transaction review',reimbursements:'Reimbursements',duplicates:'Duplicate checker',gbit:'GBITs',history:'Activity',connection:'Connection',consistency:'Consistency checker'}[name];
  if(config?.configured && ['validation','reimbursements','duplicates','gbit'].includes(name) && !autoLoadedTools.has(name)) {
    autoLoadedTools.add(name);
    if(name==='validation') await loadValidation();
    else if(name==='duplicates') await loadDuplicates();
    else if(name==='gbit') await loadGbit();
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
  $('consistency-start').value=localDate(start);$('consistency-end').value=localDate(today);
  $('start').value=localDate(start);
  $('end').value=localDate(today);
  $('duplicates-start').value=localDate(start);
  $('duplicates-end').value=localDate(today);
  const gbitStart=new Date(today);gbitStart.setDate(gbitStart.getDate()-90);
  $('gbit-start').value=localDate(gbitStart);$('gbit-end').value=localDate(today);
  try {
    config=await api('/api/bootstrap');
    $('connection-url').textContent=config.firefly_public_url||'Set FIREFLY_PUBLIC_URL to enable Open in Firefly links.';
    $('connection-state').textContent=config.configured?'Credentials configured on server. Test the connection below.':'Configuration required.';
    $('matching-rules').textContent=`Pending tag: ${config.tag}. All withdrawals carrying this tag are included, regardless of description. Change the tag using REIMBURSE_TAG.`;
    if(!config.configured){await view('connection');notice('Add your Firefly III URL and API token to the Docker environment to get started.');return;}
    $('todo-tag').textContent=config.todo_tag;
    $('mark-cash-help').textContent=`Mark as cash ${config.mark_cash_remove_todo===false?'keeps todo and':'removes todo and'} clears category, budget and subscription; transfers keep both accounts.`;
    renderStats(); renderExpenses();
    await perform(()=>view('validation'));
  } catch(e) { notice(e.message); }
})();

let validationRows=[], validationLoaded=false, validationSelected=new Set();
function visibleValidationRows() {
  const q=$('validation-search').value.toLowerCase();
  const rows=validationRows.filter(x=>[x.group_title,x.description,x.source_name,x.destination_name,x.category_name,...(x.tags||[])].join(' ').toLowerCase().includes(q));
  const order=$('validation-sort').value;
  if(order==='date-asc'||order==='date-desc')rows.sort((a,b)=>((a.date||'').localeCompare(b.date||'')||String(a.group_id).localeCompare(String(b.group_id),undefined,{numeric:true}))*(order==='date-asc'?1:-1));
  return rows;
}
function renderValidation() {
  validationSelected=new Set([...validationSelected].filter(id=>validationRows.some(row=>row.journal_id===id)));
  const rows=visibleValidationRows();
  const journalRow=(x,grouped=false)=>`<tr class="${grouped?'validation-split ':''}${validationSelected.has(x.journal_id)?'selected':''}"><td><input type="checkbox" data-review-select="${esc(x.journal_id)}" aria-label="Select ${esc(transactionIdLabel(x))}" ${validationSelected.has(x.journal_id)?'checked':''} ${busy?'disabled':''}></td><td><strong>${grouped?esc(x.description):fireflyLink(x.group_id,x.description)}</strong><small>${grouped?'':esc(x.group_title)+' · '}${esc(transactionIdLabel(x))}</small><small>Accounts: ${esc(x.source_name)} → ${esc(x.destination_name)}</small><small>Category: ${esc(x.category_name||'Uncategorized')}</small><small>Tags: ${(x.tags||[]).map(esc).join(' · ')||'None'}</small></td><td>${esc(date(x.date))}</td><td class="right">${esc(fmt(x.amount,x.currency_code))}</td><td>${grouped?'':reviewDuplicateStatus(x.duplicate_check)}</td><td><div class="row-actions">${reviewAction('validate',x.journal_id,'Mark validated')}${reviewAction('categorize',x.journal_id,'Categorize')}${reviewAction('cash',x.journal_id,'Mark as cash')}${reviewAction('reimbursement',x.journal_id,'Split transaction')}${['withdrawal','deposit'].includes(x.type)?reviewAction('gbit',x.journal_id,'Mark as GBIT'):''}${x.type==='deposit'?reviewAction('refund',x.journal_id,'Mark as Refund'):''}${grouped?'':deleteButton(x.group_id)}</div></td></tr>`;
  const groups=new Map();
  for(const row of rows) {
    const key=row.group_id||row.journal_id;
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(row);
  }
  $('validation-rows').innerHTML=[...groups.values()].map(journals=>{
    const parent=journals[0],count=parent.journal_count||journals.length;
    if(count===1)return journalRow(parent);
    const chosen=journals.filter(row=>validationSelected.has(row.journal_id)).length;
    const totals=parent.group_totals||Object.fromEntries([...new Set(journals.map(row=>row.currency_code))].map(currency=>[currency,decimal(journals.filter(row=>row.currency_code===currency).reduce((sum,row)=>sum+units(row.amount),0n))]));
    return `<tr class="validation-parent"><td><input type="checkbox" data-review-group="${esc(parent.group_id)}" data-partial="${chosen>0&&chosen<journals.length}" aria-label="Select visible journals of transaction ${esc(parent.group_id)}" ${chosen===journals.length?'checked':''} ${busy?'disabled':''}></td><td><strong>${fireflyLink(parent.group_id,parent.group_title||parent.description)}</strong><small>Transaction #${esc(parent.group_id)} · ${count} splits · ${journals.length} shown awaiting validation</small></td><td>${esc(date(parent.date))}</td><td class="right"><strong>${Object.entries(totals).map(([currency,total])=>esc(fmt(total,currency))).join(' · ')}</strong><small>${parent.group_totals?'Transaction total':'Shown splits total'}</small></td><td>${reviewDuplicateStatus(parent.duplicate_check)}</td><td><div class="row-actions">${reviewAction('validate-group',parent.group_id,'Mark transaction validated (all pending splits)')}${deleteButton(parent.group_id)}</div></td></tr>`+journals.map(row=>journalRow(row,true)).join('');
  }).join('')||`<tr><td colspan="6" class="empty">${validationLoaded?'No transactions match.':'Click Load from Firefly to see transactions awaiting validation.'}</td></tr>`;
  document.querySelectorAll('[data-review-group]').forEach(input=>input.indeterminate=input.dataset.partial==='true');
  $('validation-count').textContent=validationLoaded?`${groups.size} transactions · ${rows.length} of ${validationRows.length} journals awaiting validation`:'Not loaded';
  const visibleSelected=rows.filter(row=>validationSelected.has(row.journal_id)).length;
  $('validation-select-all').checked=rows.length>0&&visibleSelected===rows.length;
  $('validation-select-all').indeterminate=visibleSelected>0&&visibleSelected<rows.length;
  $('validation-select-all').disabled=busy||!rows.length;
  $('validation-selection-count').textContent=`${validationSelected.size} selected (${visibleSelected} visible)`;
  $('validate-selected').disabled=busy||!validationSelected.size;
  $('cash-selected').disabled=busy||!validationSelected.size;
  $('gbit-selected').disabled=busy||!validationSelected.size;
  $('categorize-selected').disabled=busy||!validationSelected.size;
  $('delete-selected').disabled=busy||!validationSelected.size;
  $('clear-validation-selection').disabled=busy||!validationSelected.size;
}
async function loadValidation() {
  notice('Loading review queue and checking nearby transactions for duplicates…');
  const result=await api('/api/validation');
  validationRows=result.transactions;validationLoaded=true;$('todo-tag').textContent=result.tag;
  renderValidation();notice('Review queue loaded.',true);
}
$('load-validation').addEventListener('click',()=>perform(loadValidation));
$('validation-sort').addEventListener('change',renderValidation);
$('validation-search').addEventListener('input',renderValidation);
$('validation-rows').addEventListener('click',event=>{
  if(busy)return;
  const deletion=event.target.closest('[data-delete]');
  if(deletion){perform(()=>previewDelete(deletion.dataset.delete));return;}
  const validateGroup=event.target.closest('[data-validate-group]');
  if(validateGroup){perform(async()=>{
    const gid=validateGroup.dataset.validateGroup;
    const result=await api('/api/validation/complete-group',{group_id:gid});
    validationRows=validationRows.filter(row=>row.group_id!==gid);
    renderValidation();notice(`Transaction marked validated (${result.validated} pending splits).`,true);
  });return;}
  const categorize=event.target.closest('[data-categorize]');
  if(categorize){perform(()=>openCategorize([categorize.dataset.categorize]));return;}
  const gbit=event.target.closest('[data-gbit]');
  if(gbit){perform(()=>flagGbit([gbit.dataset.gbit]));return;}
  const refund=event.target.closest('[data-refund]');
  if(refund){perform(()=>openRefund(refund.dataset.refund));return;}
  const reimbursement=event.target.closest('[data-reimbursement]');
  if(reimbursement){perform(()=>openReimbursement(reimbursement.dataset.reimbursement));return;}
  const cash=event.target.closest('[data-cash]');
  if(cash){perform(()=>markCash([cash.dataset.cash]));return;}
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
// Shared transaction presentation: do not hide a lone journal behind a split count.
function transactionIdLabel(row={}) {
  const count=row.journal_count??row.splits?.length;
  return count===1&&row.group_id?`Transaction #${row.group_id}`:`Journal #${row.journal_id||row.transaction_journal_id||''}`;
}
function reviewIdLabel(id) {return transactionIdLabel(validationRows.find(row=>row.journal_id===id)||{journal_id:id});}
function transactionJournalDetails(row) {
  const journalLine=s=>`<div class="review-line"><div>${esc(s.description)}<small>${esc(transactionIdLabel({...row,...s,journal_count:row.journal_count??row.splits.length}))} · ${esc(s.source)} → ${esc(s.destination)}</small></div><strong>${esc(fmt(s.amount,row.currency))}</strong></div>`;
  if(row.splits.length===1)return journalLine(row.splits[0]);
  if(!row.splits.length)return '';
  return `<details><summary>${row.splits.length} journals · Split breakdown</summary>${row.splits.map(journalLine).join('')}</details>`;
}
function duplicateCard(row, deletable=false) {
  return `<article class="duplicate-transaction"><h3>${fireflyLink(row.group_id,row.title)}</h3>${deletable?deleteButton(row.group_id):''}<p>${esc(row.date)} · ${esc(row.type)} · Transaction #${esc(row.group_id)}</p><strong>${esc(fmt(row.total,row.currency))}</strong><p>${row.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join(' ')||'No tags'}</p>${transactionJournalDetails(row)}</article>`;
}
let duplicatePairs=[],duplicateNext=null,duplicateQuery,duplicateSelected=new Set(),duplicateSelectionSeen=new Set();
function duplicateSelectableCard(row) {
  return `<div><label class="duplicate-selection"><input type="checkbox" data-duplicate-select="${esc(row.group_id)}" ${duplicateSelected.has(row.group_id)?'checked':''} ${busy?'disabled':''}> Select transaction #${esc(row.group_id)} for deletion</label>${duplicateCard(row,true)}</div>`;
}
function renderDuplicatePairs() {
  $('delete-duplicates-selected').disabled=busy||!duplicateSelected.size;
  $('clear-duplicates-selection').disabled=busy||!duplicateSelected.size;
  $('duplicates-selection-count').textContent=`${duplicateSelected.size} unique transaction${duplicateSelected.size===1?'':'s'} selected`;

  $('duplicates-results').innerHTML=duplicatePairs.map(pair=>`<section class="card duplicate-pair"><div class="duplicate-heading">Same total, currency, type and account · ${pair.days_apart} day${pair.days_apart===1?'':'s'} apart${pair.signals.length?' · '+esc(pair.signals.join(' · ')):''}</div><div class="duplicate-columns">${duplicateSelectableCard(pair.left)}${duplicateSelectableCard(pair.right)}</div></section>`).join('')||'<div class="card empty">No duplicate candidates found in this range.</div>';
}
async function loadDuplicates(append=false) {
  const start=$('duplicates-start').value,end=$('duplicates-end').value,days=$('duplicates-days').value;
  if(!append&&(!start||!end||start>end)) throw new Error('Choose a valid duplicate-check date range.');
  if(!append&&(!/^\d+$/.test(days)||Number(days)>31)) throw new Error('Days apart must be a whole number between 0 and 31.');
  notice('Checking transaction totals for duplicates…');
  const query=append?{...duplicateQuery,offset:duplicateNext}:{start,end,days};
  const result=await api('/api/duplicates?'+new URLSearchParams(query));
  if(!append) {
    const sameQuery=duplicateQuery&&duplicateQuery.start===start&&duplicateQuery.end===end&&duplicateQuery.days===days;
    if(!sameQuery){duplicateSelected.clear();duplicateSelectionSeen.clear();}
    duplicateQuery={start,end,days};
  }
  for(const pair of result.pairs)for(const row of [pair.left,pair.right]) {
    if(!duplicateSelectionSeen.has(row.group_id)) {
      duplicateSelectionSeen.add(row.group_id);
      if((row.tags||[]).includes(config.todo_tag||'todo'))duplicateSelected.add(row.group_id);
    }
  }
  duplicatePairs=append?duplicatePairs.concat(result.pairs):result.pairs;
  duplicateNext=result.next_offset??null;
  $('more-duplicates').hidden=duplicateNext===null;
  $('duplicates-summary').textContent=`${result.scanned} transactions scanned · ${duplicatePairs.length} candidate pairs shown${duplicateNext!==null?' (more available below)':' (all loaded)'} · ${result.skipped.length} needing manual review`;
  renderDuplicatePairs();
  $('duplicates-skipped').hidden=!result.skipped.length;
  $('duplicates-skipped-list').innerHTML=result.skipped.map(row=>`<p>${fireflyLink(row.group_id,row.title)}: ${esc(row.reason)}</p>`).join('');
  notice(duplicateNext!==null?'More duplicate candidates are available. Click Load more candidates below the results.':'All duplicate candidates loaded. Candidates require manual review.',duplicateNext===null);
}
$('duplicates-results').addEventListener('change',event=>{
  const id=event.target.dataset.duplicateSelect;
  if(!id||busy)return;
  if(event.target.checked)duplicateSelected.add(id);else duplicateSelected.delete(id);
  renderDuplicatePairs();
});
$('delete-duplicates-selected').addEventListener('click',()=>perform(()=>previewDeletes([...duplicateSelected],'duplicates')));
$('clear-duplicates-selection').addEventListener('click',()=>{if(!busy){duplicateSelected.clear();renderDuplicatePairs();}});
$('duplicates-results').addEventListener('click',event=>{
  const button=event.target.closest('[data-delete]');
  if(button&&!busy)return perform(()=>previewDelete(button.dataset.delete,'duplicates'));
});
$('load-duplicates').addEventListener('click',()=>perform(()=>loadDuplicates()));
$('more-duplicates').addEventListener('click',()=>perform(()=>loadDuplicates(true)));

function reviewDuplicateStatus(check) {
  if(!check) return '<span class="muted">Not checked</span>';
  if(check.status!=='checked') return `<span class="duplicate-alert">${check.status==='manual'?'Manual review needed':'Check unavailable'}</span><small>${esc(check.reason)}</small>`;
  if(!check.match_count) return `<span class="muted">No candidates within ±${check.days} days</span>`;
  return `<details class="review-duplicates"><summary class="duplicate-alert">${check.match_count} potential duplicate${check.match_count===1?'':'s'}</summary><p>Same parent total, currency, type and account. Review before validating.</p>${check.matches.map(match=>`<div class="review-duplicate-match"><p>${match.days_apart} days apart${match.signals.length?' · '+esc(match.signals.join(' · ')):''}</p>${duplicateCard(match.transaction,true)}</div>`).join('')}${check.truncated?'<p>Showing the first 20 matches.</p>':''}</details>`;
}

let deletionPreview,deletionSource;
function reviewAction(action,id,label) {
  const paths={
    'validate-group':'<path d="m5 12 4 4L19 6"/>',
    validate:'<path d="m5 12 4 4L19 6"/>',
    categorize:'<path d="M20 13 11 22 2 13V4h9l9 9Z" transform="translate(1 -1) scale(.9)"/><circle cx="7" cy="7" r="1"/>',
    reimbursement:'<path d="M6 3v5c0 3 12 3 12 6v7M6 8v13M3 18l3 3 3-3M15 18l3 3 3-3"/>',
    cash:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M16 10h5v5h-5a2.5 2.5 0 0 1 0-5Z"/><path d="M6 5V3h12"/>',
    gbit:'<path d="M3 10a9 9 0 1 1 2 8M3 4v6h6M12 7v5l3 2"/>',
    refund:'<path d="m9 4-6 6 6 6M3 10h11a6 6 0 0 1 0 12" transform="translate(1 -1) scale(.9)"/>',
    delete:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>'
  };
  return `<button type="button" class="icon-action ${action==='delete'?'danger-icon':['validate','validate-group'].includes(action)?'success-icon':''}" data-${action}="${esc(id)}" title="${esc(label)}" aria-label="${esc(label)}" ${busy?'disabled':''}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths[action]||''}</svg></button>`;
}
function deleteButton(groupId) {return reviewAction('delete',groupId,'Delete transaction');}
function deletionCard(preview) {
  const group=preview.transaction,splits=group.attributes.transactions;
  return `<h3>${fireflyLink(preview.group_id,group.attributes.group_title||splits[0]?.description||'Transaction')}</h3><p>Transaction #${esc(preview.group_id)} · ${splits.length===1?'The transaction will be deleted.':splits.length+' journals will be deleted.'}</p>`+splits.map(s=>`<div class="review-line"><div>${esc(s.description)}<small>${esc(transactionIdLabel({...s,group_id:preview.group_id,journal_count:splits.length}))} · ${esc(date(s.date))} · ${esc(s.source_name)} → ${esc(s.destination_name)}</small><p>${(s.tags||[]).map(esc).join(' · ')}</p></div><strong>${esc(fmt(s.amount,s.currency_code))}</strong></div>`).join('');
}
async function previewDeletes(groupIds,source='validation') {
  deletionSource=source;
  deletionPreview=undefined;
  const ids=[...new Set(groupIds)];
  if(!ids.length)throw new Error('Select transactions to delete.');
  if(ids.length>100)throw new Error('Select at most 100 parent transactions per deletion.');
  const previews=[];
  for(const group_id of ids)previews.push(await api('/api/validation/delete-preview',{group_id}));
  deletionPreview=previews;
  $('delete-content').innerHTML=`<p><strong>${previews.length} parent transaction${previews.length===1?'':'s'} will be deleted, including all journals—even unselected splits.</strong></p>`+previews.map(deletionCard).join('');
  $('confirm-delete').textContent=previews.length===1?'Delete entire transaction':`Delete ${previews.length} entire transactions`;
  $('delete-dialog').showModal();
}
async function previewDelete(groupId,source='validation') {return previewDeletes([groupId],source);}
$('delete-selected').addEventListener('click',()=>perform(()=>previewDeletes(validationRows.filter(row=>validationSelected.has(row.journal_id)).map(row=>row.group_id))));
$('cancel-delete').addEventListener('click',()=>{deletionPreview=undefined;$('delete-dialog').close();});
$('delete-dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault();else deletionPreview=undefined;});
function removeDeletedTransaction(gid) {
  duplicateSelected.delete(gid);
  duplicatePairs=duplicatePairs.filter(pair=>pair.left.group_id!==gid&&pair.right.group_id!==gid);
  duplicateNext=null;
  $('more-duplicates').hidden=true;
  renderDuplicatePairs();
  $('duplicates-summary').textContent=`${duplicatePairs.length} candidate pairs remain in the loaded results. Reload to refresh the full check.`;
  for(const row of validationRows)if(row.group_id===gid)validationSelected.delete(row.journal_id);
  validationRows=validationRows.filter(row=>row.group_id!==gid);
  data.expenses=data.expenses.filter(row=>row.group_id!==gid);
  data.deposits=data.deposits.filter(row=>row.group_id!==gid);
  for(const row of validationRows) {
    const check=row.duplicate_check;
    if(check?.status==='checked') {check.matches=check.matches.filter(m=>m.transaction.group_id!==gid);check.match_count=check.matches.length;}
  }
}
$('confirm-delete').addEventListener('click',()=>perform(async()=>{
  if(!deletionPreview?.length)throw new Error('Open a deletion preview first.');
  const previews=deletionPreview,source=deletionSource;
  deletionPreview=undefined;
  let completed=0,failure='';
  for(const preview of previews) {
    try {
      const result=await api('/api/validation/delete',{token:preview.token});
      removeDeletedTransaction(result.group_id);completed++;
    }catch(error){failure=`Stopped at transaction #${preview.group_id}: ${error.message} Inspect Activity before retrying; the last deletion may have completed.`;break;}
  }
  $('delete-dialog').close();
  for(const tool of ['duplicates','reimbursements','gbit'])autoLoadedTools.delete(tool);
  renderValidation();renderStats();renderExpenses();
  let reloadError='';
  try {await loadValidation();}catch(error){reloadError=' Reload the queue: '+error.message;}
  if(source==='duplicates') {
    try {await loadDuplicates();autoLoadedTools.add('duplicates');}
    catch(error){reloadError+=' Reload the duplicate checker: '+error.message;}
  }
  notice(`${completed} of ${previews.length} parent transactions deleted, including all their splits.${failure?' '+failure:''}${reloadError}`,!failure&&!reloadError);
}));

let activityEvents=[],activityOffset=null,activityPrevious=null,activityQuery;
function activityTransactionLink(groupId,snapshot={}) {
  const row=snapshot?.attributes||snapshot||{};
  const descriptions=[...new Set((row.transactions||[]).map(split=>split.description).filter(Boolean))].join(' · ');
  const description=row.group_title||row.title||row.description||descriptions;
  return fireflyLink(groupId,`#${groupId}${description?' · '+description:''}`);
}
function gbitActivityCard(event) {
  const rows=event.plan.rows;
  return `<article class="card history-card"><div class="history-heading"><strong>GBIT · ${activityTransactionLink(rows.original_id.group_id,rows.original_id)}</strong><span class="status">${esc(gbitStateLabel(event.operation_state))}</span></div><p>${activityTimestamp(event.created)} · ${esc(fmt(rows.original_id.total,rows.original_id.currency))}</p><p>${activityTransactionLink(rows.original_id.group_id,rows.original_id)} → ${activityTransactionLink(rows.new_id.group_id,rows.new_id)}${rows.refund_id?' · '+activityTransactionLink(rows.refund_id.group_id,rows.refund_id):' · No refund selected'}</p>${event.result?.error?`<p class="duplicate-alert">${esc(event.result.error)}</p>`:''}<button class="secondary" data-activity-gbit="${esc(event.plan_id)}">${event.operation_state==='complete'?'Inspect & verify links':'Inspect & resume'}</button></article>`;
}
function reimbursementActivityCard(event) {
  const saved=event.plan,result=event.result;
  return `<article class="card history-card"><div class="history-heading"><strong>Reimbursement · ${activityTransactionLink(saved.deposit.group_id,saved.deposit)}</strong><span class="status">${esc(event.state)}</span></div><p>${activityTimestamp(event.created)} · ${esc(fmt(saved.total,saved.currency))} · ${esc(transactionIdLabel(saved.deposit))}</p><p>${saved.expenses.map(expense=>activityTransactionLink(expense.group_id,expense)).join(' · ')}</p>${result?.items?.length?`<ul>${result.items.map(item=>`<li>${esc(transactionIdLabel(saved.expenses.find(expense=>expense.journal_id===item.journal_id)||item))}: ${esc(item.status)}${item.error?' — '+esc(item.error):''}</li>`).join('')}</ul>`:''}<button class="secondary" data-resume-reimbursement="${esc(event.plan_id)}">${event.state==='completed'?'Inspect & verify links':event.operation_state==='review'?'Open review':'Inspect & retry'}</button></article>`;
}
$('activity-list').addEventListener('click',event=>{
  const gbitButton=event.target.closest('[data-activity-gbit]');
  if(gbitButton?.dataset.activityGbit&&!busy)return perform(async()=>showGbitReview(await api('/api/gbit/plan?'+new URLSearchParams({plan_id:gbitButton.dataset.activityGbit}))));
  const button=event.target.closest('[data-resume-reimbursement]');
  if(button&&!busy)return perform(async()=>renderPlan(await api('/api/reimbursements/plan?'+new URLSearchParams({plan_id:button.dataset.resumeReimbursement}))));
});
function activityPageControls() {
  $('previous-activity').disabled=busy||activityPrevious===null;
  $('more-activity').disabled=busy||activityOffset===null;
}
function readActivityFilters() {
  const query={limit:$('activity-limit').value||'25',action:$('activity-action').value,state:$('activity-state').value,
    group_id:$('activity-group').value.trim(),start:$('activity-start').value,end:$('activity-end').value};
  if(query.group_id&&!/^\d+$/.test(query.group_id))throw new Error('Enter a numeric transaction ID.');
  if(query.start&&query.end&&query.start>query.end)throw new Error('Choose a valid activity date range.');
  return query;
}
async function loadActivity(offset=0) {
  if(!activityQuery)activityQuery=readActivityFilters();
  const result=await api('/api/activity?'+new URLSearchParams({...activityQuery,offset}));
  activityEvents=result.events;
  activityOffset=result.next_offset;
  activityPrevious=result.previous_offset??null;
  const action=activityQuery.action;
  $('activity-action').innerHTML='<option value="">All actions</option>'+[...new Set([...(result.actions||[]),...(action?[action]:[])])].map(value=>`<option value="${esc(value)}">${esc(value)}</option>`).join('');
  $('activity-action').value=action;
  const total=result.total??activityEvents.length,limit=result.limit||Number(activityQuery.limit),current=result.offset||0;
  $('activity-page').textContent=total?`Page ${Math.floor(current/limit)+1} of ${Math.ceil(total/limit)} · ${current+1}–${current+activityEvents.length} of ${total} changes`:'No matching changes';
  $('activity-list').innerHTML=activityEvents.map(event=>event.entry_type==='gbit'?gbitActivityCard(event):event.entry_type==='reimbursement'?reimbursementActivityCard(event):`<article class="card history-card"><div class="history-heading"><strong>${esc(event.action)}</strong><span class="status">${esc(event.state)}</span></div><p>${activityTimestamp(event.created)} · ${esc(event.method)} ${esc(event.path)}</p>${event.group_id?`<p>${activityTransactionLink(event.group_id,event.display_transaction||event.after||event.before||event.response?.data||event.request)}${event.method==='DELETE'?' (may no longer exist in Firefly)':''}</p>`:''}${(event.tag_changes||[]).map(change=>`<p>${esc(transactionIdLabel({journal_id:change.journal_id,group_id:event.group_id,journal_count:(event.before||event.after)?.attributes?.transactions?.length}))}: ${esc(change.before.join(', ')||'No tags')} → ${esc(change.after.join(', ')||'No tags')}</p>`).join('')}${event.error?`<p class="duplicate-alert">${esc(event.error)}</p>`:''}${event.verification_note?`<p>${esc(event.verification_note)}</p>`:''}<details><summary>Request and transaction snapshots</summary><pre class="audit-json">${esc(JSON.stringify({request:event.request,before:event.before,after:event.after,response:event.response},null,2))}</pre></details></article>`).join('')||'<div class="card empty">No recorded Firefly changes yet.</div>';
  $('more-activity').hidden=activityOffset===null;
  activityPageControls();
}
$('more-activity').addEventListener('click',()=>perform(()=>loadActivity(activityOffset)));
$('previous-activity').addEventListener('click',()=>perform(()=>loadActivity(activityPrevious)));
$('activity-filters').addEventListener('submit',event=>{event.preventDefault();return perform(async()=>{const query=readActivityFilters();activityQuery=query;await loadActivity();});});
$('reset-activity-filters').addEventListener('click',()=>perform(async()=>{
  for(const id of ['activity-action','activity-state','activity-group','activity-start','activity-end'])$(id).value='';
  $('activity-limit').value='25';activityQuery=undefined;await loadActivity();
}));

$('validation-rows').addEventListener('change',event=>{
  if(busy)return;
  const group=event.target.dataset.reviewGroup;
  if(group) {
    for(const row of visibleValidationRows().filter(row=>row.group_id===group))event.target.checked?validationSelected.add(row.journal_id):validationSelected.delete(row.journal_id);
    renderValidation();return;
  }
  const id=event.target.dataset.reviewSelect;
  if(!id)return;
  event.target.checked?validationSelected.add(id):validationSelected.delete(id);
  renderValidation();
});
$('validation-select-all').addEventListener('change',event=>{
  if(busy)return;
  for(const row of visibleValidationRows())event.target.checked?validationSelected.add(row.journal_id):validationSelected.delete(row.journal_id);
  renderValidation();
});
$('clear-validation-selection').addEventListener('click',()=>{if(!busy){validationSelected.clear();renderValidation();}});
async function validateSelected() {
  const ids=[...validationSelected];
  let completed=0;
  const failures=[];
  for(const id of ids) {
    notice(`Validating selected transactions: ${completed+failures.length+1} of ${ids.length}…`);
    try {
      await api('/api/validation/complete',{journal_id:id});
      validationRows=validationRows.filter(row=>row.journal_id!==id);
      validationSelected.delete(id);completed++;
    } catch(error) {failures.push(`${reviewIdLabel(id)}: ${error.message}`);}
    renderValidation();
  }
  notice(`${completed} transaction${completed===1?'':'s'} marked validated.${failures.length?' '+failures.length+' failed and remain selected.\n'+failures.join('\n'):''}`,!failures.length);
}
$('validate-selected').addEventListener('click',()=>perform(validateSelected));

async function markCash(ids) {
  let completed=0;
  const failures=[];
  for(const id of ids) {
    notice(`Marking as cash: ${completed+failures.length+1} of ${ids.length}…`);
    try {
      await api('/api/validation/mark-cash',{journal_id:id});
      if(config.mark_cash_remove_todo!==false)validationRows=validationRows.filter(row=>row.journal_id!==id);
      validationSelected.delete(id);completed++;
    } catch(error) {failures.push(`${reviewIdLabel(id)}: ${error.message}`);}
  }
  autoLoadedTools.delete('duplicates');autoLoadedTools.delete('reimbursements');
  let reloadError='';
  try {await loadValidation();}catch(error){reloadError=`\nChanges may have completed. Reload the queue: ${error.message}`;}
  notice(`${completed} transaction${completed===1?'':'s'} marked as cash. ${config.mark_cash_remove_todo===false?'Todo and other tags kept.':'Todo tag removed; other tags kept.'}${failures.length?'\n'+failures.join('\n'):''}${reloadError}`,!failures.length&&!reloadError);
}
$('cash-selected').addEventListener('click',()=>perform(()=>markCash([...validationSelected])));

let refundDepositId,refundSearch,refundSelection,refundJournals=new Set();
function refundSelectionControls() {
  $('confirm-refund').disabled=busy||!refundSelection||!refundJournals.size;
  const row=refundSearch?.candidates.find(row=>row.group_id===refundSelection);
  if(!row)return;
  const chosen=row.splits.filter(split=>refundJournals.has(split.journal_id));
  const total=decimal(chosen.reduce((sum,split)=>sum+units(split.amount),0n));
  $('refund-status').textContent=`${chosen.length} selected · ${fmt(total,row.currency)}. Deposit: ${fmt(refundSearch.deposit.amount,refundSearch.deposit.currency_code)}.${units(total)!==units(refundSearch.deposit.amount)?' Amounts differ; review the selection before confirming.':''}`;
}
async function openRefund(id) {
  refundDepositId=id;refundSearch=undefined;refundSelection=undefined;refundJournals.clear();
  $('refund-remove-todo').checked=false;
  $('refund-same-account').checked=true;
  $('refund-candidates').innerHTML='';$('refund-status').textContent='Loading withdrawals…';
  $('refund-dialog').showModal();
  await searchRefund(true);
}
async function searchRefund(defaults=false) {
  const body={deposit_id:refundDepositId,same_account:$('refund-same-account').checked};
  if(!defaults)Object.assign(body,{start:$('refund-start').value,end:$('refund-end').value,tolerance:$('refund-tolerance').value});
  $('refund-status').textContent='Loading eligible withdrawals…';
  refundSearch=undefined;refundSelection=undefined;refundJournals.clear();$('confirm-refund').disabled=true;
  let result;
  try {result=await api('/api/validation/refund-candidates',body);}
  catch(error){$('refund-status').textContent=error.message;throw error;}
  refundSearch=result;
  $('refund-same-account').checked=result.same_account;
  $('refund-start').value=result.start;$('refund-end').value=result.end;$('refund-tolerance').value=result.tolerance;
  $('refund-deposit').innerHTML=`${fireflyLink(result.deposit.group_id,result.deposit.description)} · ${esc(fmt(result.deposit.amount,result.deposit.currency_code))} · ${esc(date(result.deposit.date))}`;
  $('refund-candidates').innerHTML=result.candidates.map(row=>`<div class="card refund-option"><label><input type="radio" name="refund-withdrawal" value="${esc(row.group_id)}"> Select transaction #${esc(row.group_id)}</label>${refundWithdrawalCard(row)}${row.splits.length>1?`<fieldset><legend>Splits to refund</legend>${row.splits.map(split=>`<label class="gbit-journal-choice"><input type="checkbox" data-refund-group="${esc(row.group_id)}" data-refund-journal="${esc(split.journal_id)}"><span>${esc(split.description)} · ${esc(fmt(split.amount,row.currency))}<small>Journal #${esc(split.journal_id)} · ${esc(split.source)} → ${esc(split.destination)}</small></span></label>`).join('')}</fieldset>`:''}<p>Whole-transaction difference from deposit: ${esc(fmt(row.difference,row.currency))}</p></div>`).join('')||'<p>No withdrawals match these dates and amount tolerance.</p>';
  $('refund-status').textContent=`${result.candidates.length} candidates. ${result.skipped.length} unsupported groups excluded (mixed currencies/accounts/dates or invalid amounts).`;
}
$('load-refund').addEventListener('click',()=>perform(()=>searchRefund()));
$('refund-candidates').addEventListener('change',event=>{
  if(busy)return;
  const target=event.target;
  if(target.dataset?.refundJournal) {
    if(refundSelection!==target.dataset.refundGroup) {
      refundSelection=target.dataset.refundGroup;refundJournals.clear();
    }
    if(target.checked)refundJournals.add(target.dataset.refundJournal);else refundJournals.delete(target.dataset.refundJournal);
  } else if(target.name==='refund-withdrawal') {
    if(refundSelection!==target.value)refundJournals.clear();
    refundSelection=target.value;
    const row=refundSearch.candidates.find(row=>row.group_id===refundSelection);
    if(row?.splits.length===1)refundJournals=new Set([row.splits[0].journal_id]);
  } else return;
  document.querySelectorAll('[name="refund-withdrawal"]').forEach(input=>input.checked=input.value===refundSelection);
  document.querySelectorAll('[data-refund-journal]').forEach(input=>input.checked=input.dataset.refundGroup===refundSelection&&refundJournals.has(input.dataset.refundJournal));
  refundSelectionControls();
});
$('cancel-refund').addEventListener('click',()=>{$('refund-dialog').close();refundSelection=undefined;refundJournals.clear();});
$('refund-dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault();});
$('confirm-refund').addEventListener('click',()=>perform(async()=>{
  if(!refundSearch||!refundSelection||!refundJournals.size)throw new Error('Choose at least one withdrawal split first.');
  $('refund-status').textContent='Creating and verifying Refund links…';
  try {
    const result=await api('/api/validation/mark-refund',{token:refundSearch.token,group_id:refundSelection,journal_ids:[...refundJournals],remove_todo:$('refund-remove-todo').checked});
    $('refund-dialog').close();refundSelection=undefined;refundJournals.clear();
    autoLoadedTools.delete('duplicates');autoLoadedTools.delete('reimbursements');
    try {await loadValidation();notice(`Refund linked (${result.links} journal links) and the deposit and selected splits marked as cash.${result.todo_removed?' Todo tag removed.':' Todo tag kept.'}`,true);}
    catch(error){notice(`Refund links created. Reload the queue: ${error.message}`);}
  } catch(error) {$('refund-status').textContent=error.message+' Some links may exist already; inspect Activity or retry this selection.';throw error;}
}));

function refundWithdrawalCard(row) { return duplicateCard(row); }
$('refund-same-account').addEventListener('change',()=>{if(!busy)perform(()=>searchRefund());});

let gbitData={new_expenses:[],refunds:[],originals:[],operations:[]},gbitPlan;
let gbitOriginalGroup='',gbitOriginalJournals=new Set(),gbitRefundJournals=new Set();
function gbitSelected() {
  return {new_id:gbitData.new_expenses.find(r=>r.group_id===$('gbit-new').value),
          original_id:gbitData.originals.find(r=>r.group_id===$('gbit-original').value),
          refund_id:gbitData.refunds.find(r=>r.group_id===$('gbit-refund').value)};
}
function gbitOptions(id,rows,placeholder) {
  const before=$(id).value;
  $(id).innerHTML=`<option value="">${esc(placeholder)}</option>`+rows.map(row=>`<option value="${esc(row.group_id)}">${esc(row.date)} · ${esc(row.title)} · ${esc(fmt(row.total,row.currency))} · #${esc(row.group_id)}</option>`).join('');
  $(id).value=rows.some(row=>row.group_id===before)?before:'';
}
function renderGbitDetails() {
  const rows=gbitSelected(),original=rows.original_id;
  if((original?.group_id||'')!==gbitOriginalGroup) {
    gbitOriginalGroup=original?.group_id||'';
    gbitRefundJournals=new Set(original?.splits.length===1?[original.splits[0].journal_id]:[]);
    gbitOriginalJournals=new Set(original?.splits.length===1?[original.splits[0].journal_id]:[]);
  }
  if(original?.splits.length===1) {gbitOriginalJournals=new Set([original.splits[0].journal_id]);gbitRefundJournals=new Set([original.splits[0].journal_id]);}
  // Discard selections removed by a manual reload.
  const available=new Set((original?.splits||[]).map(split=>split.journal_id));
  gbitOriginalJournals=new Set([...gbitOriginalJournals].filter(id=>available.has(id)));
  gbitRefundJournals=new Set([...gbitRefundJournals].filter(id=>available.has(id)));
  $('gbit-refund-journals').innerHTML=original?.splits.length>1&&rows.refund_id?
    `<fieldset><legend>Original splits refunded by this deposit</legend><p class="muted">Choose one or more splits. This selection is independent of the new-charge links.</p>${original.splits.map(split=>`<label class="gbit-journal-choice"><input type="checkbox" data-gbit-refund-journal="${esc(split.journal_id)}" ${gbitRefundJournals.has(split.journal_id)?'checked':''} ${busy?'disabled':''}><span><strong>${esc(split.description)}</strong> · ${esc(fmt(split.amount,original.currency))}<small>Journal #${esc(split.journal_id)} · ${esc(split.source)} → ${esc(split.destination)}</small></span></label>`).join('')}</fieldset>`:'';
  $('gbit-original-journals').innerHTML=original?.splits.length>1?
    `<fieldset><legend>Original journals for the new charge · ${fireflyLink(original.group_id,'Open in Firefly')}</legend><p class="muted">Select the expense journals to link. Leave unrelated fees unchecked.</p>${original.splits.map(split=>`<label class="gbit-journal-choice"><input type="checkbox" data-gbit-journal="${esc(split.journal_id)}" ${gbitOriginalJournals.has(split.journal_id)?'checked':''} ${busy?'disabled':''}><span><strong>${esc(split.description)}</strong> · ${esc(fmt(split.amount,original.currency))}<small>Journal #${esc(split.journal_id)} · ${esc(split.source)} → ${esc(split.destination)}</small></span></label>`).join('')}</fieldset>`:'';
  if(original) {
    const splits=original.splits.filter(split=>gbitOriginalJournals.has(split.journal_id));
    rows.original_id=splits.length?{...original,journal_count:original.journal_count??original.splits.length,splits,total:decimal(splits.reduce((sum,split)=>sum+units(split.amount),0n))}:undefined;
  }
  const valid=rows.new_id&&rows.original_id&&(!rows.refund_id||gbitRefundJournals.size>0);
  $('review-gbit').disabled=busy||!valid||new Set(Object.values(rows).filter(Boolean).map(r=>r.currency)).size>1;
  let refundOriginal;
  if(original&&rows.refund_id&&gbitRefundJournals.size) {
    const splits=original.splits.filter(split=>gbitRefundJournals.has(split.journal_id));
    refundOriginal={...original,journal_count:original.journal_count??original.splits.length,splits,total:decimal(splits.reduce((sum,split)=>sum+units(split.amount),0n))};
  }
  $('gbit-details').innerHTML=Object.entries(rows).filter(([,row])=>row).map(([name,row])=>`<h3>${{new_id:'New card charge',original_id:'Original expense — selected journals',refund_id:'Refund deposit'}[name]}</h3>${name==='refund_id'?gbitRefundCard(row,refundOriginal):duplicateCard(row)}`).join('');
  const chosen=Object.values(rows).filter(Boolean);
  const mismatch=chosen.length>1&&chosen.some(row=>row.currency!==chosen[0].currency||units(row.total)!==units(chosen[0].total));
  $('gbit-balance').textContent=mismatch?'Amounts differ. You can still review, provided the currency matches.':valid?'Amounts match. Review the transactions before linking.':'Choose a new charge and the original expense.';
  if(original&&rows.refund_id&&!gbitRefundJournals.size)$('gbit-balance').textContent='Choose at least one original split to link to the refund deposit.';
  if(valid&&!rows.refund_id)$('gbit-balance').textContent+=' The GBIT stays incomplete and tagged until its refund is matched.';
  if(original&&rows.refund_id&&gbitRefundJournals.size) {
    const total=original.splits.filter(split=>gbitRefundJournals.has(split.journal_id)).reduce((sum,split)=>sum+units(split.amount),0n);
    if(total!==units(rows.refund_id.total))$('gbit-balance').textContent+=` Selected refund splits total ${fmt(decimal(total),original.currency)}; refund deposit ${fmt(rows.refund_id.total,rows.refund_id.currency)}. You can still review this difference.`;
  }
}
function renderGbitOriginals() {
  const q=$('gbit-search').value.trim().toLocaleLowerCase();
  const matches=gbitData.originals.filter(row=>[
    row.title,row.group_id,row.date,row.total,row.currency,fmt(row.total,row.currency),
    ...(row.tags||[]),
    ...(row.splits||[]).flatMap(split=>[split.description,split.journal_id,split.source,split.destination])
  ].join(' ').toLocaleLowerCase().includes(q));
  gbitOptions('gbit-original',matches,'Select the original expense…');
  renderGbitDetails();
}
function groupedGbitOperations(operations) {
  const groups=new Map();
  for(const op of operations) {
    const rows=op.plan.rows;
    // Journal choices are revisions of a match, not separate card moves.
    const key=JSON.stringify([String(rows.original_id.group_id),String(rows.new_id.group_id)]);
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(op);
  }
  const rank=op=>op.state==='complete'?100:op.state==='awaiting_refund'?60:['partial','applying'].includes(op.state)?(op.plan.rows.refund_id?80:40):20;
  return [...groups.values()].map(attempts=>{
    attempts.sort((a,b)=>rank(b)-rank(a)||(b.created||'').localeCompare(a.created||''));
    return {operation:attempts[0],attempts,latest:attempts.map(op=>op.created||'').sort().at(-1)};
  }).sort((a,b)=>b.latest.localeCompare(a.latest));
}
function gbitStateLabel(state) {
  return {review:'Ready to review',awaiting_refund:'Awaiting refund',partial:'Needs attention',applying:'Interrupted — inspect before retrying',complete:'Complete'}[state]||state;
}
function gbitAccountCard(row,label) {
  const accounts=[...new Set((row.splits||[]).map(s=>s.source).filter(Boolean))].join(' · ')||'Account unavailable';
  return `<section class="gbit-account"><span class="gbit-role">${esc(label)}</span><h3>${esc(accounts)}</h3><div class="gbit-transaction">${fireflyLink(row.group_id,row.title)}</div><strong>${esc(fmt(row.total,row.currency))}</strong><span class="gbit-date">${esc(date(row.date))}</span>${transactionJournalDetails(row)}</section>`;
}
function renderSavedGbits() {
  const groups=groupedGbitOperations(gbitData.operations).filter(group=>group.operation.state!=='complete');
  $('gbit-operations').innerHTML=groups.map(({operation:op,attempts})=>{
    const rows=op.plan.rows,refund=rows.refund_id;
    const resume=!['complete','awaiting_refund'].includes(op.state);
    return `<article class="card gbit-operation"><div class="history-heading"><div><span class="eyebrow">GO BACK IN TIME</span><h3>${fireflyLink(rows.original_id.group_id,rows.original_id.title)}</h3></div><span class="gbit-state gbit-state-${esc(op.state)}">${esc(gbitStateLabel(op.state))}</span></div><div class="gbit-move">${gbitAccountCard(rows.original_id,'Original expense')}<div class="gbit-direction"><span aria-hidden="true">→</span><small>${['complete','awaiting_refund'].includes(op.state)?'Moved to':'Move to'}</small></div>${gbitAccountCard(rows.new_id,'New card charge')}</div><div class="gbit-refund"><span class="gbit-refund-icon" aria-hidden="true">↶</span><div><strong>${refund?'Refund deposit':'Refund not matched yet'}</strong>${refund?`<p>${fireflyLink(refund.group_id,refund.title)} · ${esc(fmt(refund.total,refund.currency))} · ${esc(date(refund.date))}</p>${transactionJournalDetails(refund)}`:'<p>The GBIT stays incomplete until its refund is linked.</p>'}</div></div><footer class="gbit-operation-footer"><div><strong>${esc({complete:'Both GBIT link types verified',awaiting_refund:'New charge linked · refund still needed',review:'Review saved · links not yet confirmed',partial:'Operation paused · inspect and retry',applying:'Last attempt did not finish'}[op.state]||gbitStateLabel(op.state))}</strong><small>Saved ${activityTimestamp(op.created)} · status from the saved operation</small></div>${resume?`<button class="secondary" data-resume-gbit="${esc(op.plan.id)}">Inspect & resume</button>`:op.state==='awaiting_refund'?`<button class="secondary" data-continue-gbit="${esc(op.plan.id)}">Match refund</button>`:''}</footer>${op.result?.error?`<p class="duplicate-alert">${esc(op.result.error)}</p>`:''}${attempts.length>1?`<details class="gbit-attempts"><summary>${attempts.length} saved attempts · one GBIT</summary><p class="muted">Earlier reviews and retries are kept here. Each button opens that attempt's exact saved selection.</p>${attempts.map(attempt=>`<div class="gbit-attempt"><div><strong>${esc(gbitStateLabel(attempt.state))}</strong><small>${activityTimestamp(attempt.created)}${attempt.plan.rows.refund_id?' · Refund #'+esc(attempt.plan.rows.refund_id.group_id):' · No refund selected'}</small><small>Original selection: ${esc(fmt(attempt.plan.rows.original_id.total,attempt.plan.rows.original_id.currency))} · Journals ${(attempt.plan.original_journal_ids||attempt.plan.rows.original_id.splits.map(split=>split.journal_id)).map(esc).join(', ')}</small>${attempt.result?.error?`<p>${esc(attempt.result.error)}</p>`:''}</div><button class="secondary" data-resume-gbit="${esc(attempt.plan.id)}">${attempt.state==='complete'?'Inspect':'Inspect & resume'}</button></div>`).join('')}</details>`:''}</article>`;
  }).join('')||'<div class="card empty">No incomplete GBITs. Completed operations are available in Activity.</div>';
}

async function loadGbit() {
  const start=$('gbit-start').value,end=$('gbit-end').value;
  if(!start||!end||start>end)throw new Error('Choose a valid original-expense date range.');
  notice('Loading pending GBIT charges, refunds and original expenses…');
  gbitData=await api('/api/gbit?'+new URLSearchParams({start,end}));
  gbitOptions('gbit-new',gbitData.new_expenses,'Select a pending GBIT withdrawal…');
  gbitOptions('gbit-refund',gbitData.refunds,'Refund has not arrived yet');
  renderGbitOriginals();
  $('gbit-summary').textContent=`${gbitData.new_expenses.length} pending new charges · ${gbitData.refunds.length} pending refunds · ${gbitData.originals.length} original expenses · ${gbitData.skipped.length} unsupported groups`;
  renderSavedGbits();
  notice('GBIT workspace loaded.',true);
}
async function flagGbit(ids) {
  const seen=new Set(),failures=[];let count=0;
  const targets=ids.map(id=>({id,row:validationRows.find(r=>r.journal_id===id)}));
  for(const {id,row} of targets) {
    if(row&&seen.has(row.group_id))continue;
    if(row)seen.add(row.group_id);
    try {
      const result=await api('/api/validation/mark-gbit',{journal_id:id});
      validationRows=validationRows.filter(r=>r.group_id!==result.group_id);count++;
    }catch(error){failures.push(`${reviewIdLabel(id)}: ${error.message}`);}
  }
  autoLoadedTools.delete('gbit');autoLoadedTools.delete('duplicates');autoLoadedTools.delete('reimbursements');
  renderValidation();notice(`${count} transaction${count===1?'':'s'} marked as GBIT (cash applied, todo removed).${failures.length?'\n'+failures.join('\n')+'\nSome cash changes may have completed. Reload Transaction review or inspect Activity.':''}`,!failures.length);
}
function gbitRefundCard(row,originalSelection) {
  const card=duplicateCard(row);
  if(!originalSelection)return card;
  const breakdown=`<div class="gbit-refund-selection"><p class="muted">Refunds ${fireflyLink(originalSelection.group_id,'selected original journals')} · ${esc(fmt(originalSelection.total,originalSelection.currency))}</p>${transactionJournalDetails(originalSelection)}</div>`;
  return card.replace(/<\/article>$/,()=>breakdown+'</article>');
}
function showGbitReview(plan) {
  gbitPlan=plan;
  $('gbit-review-status').textContent='';
  $('gbit-review-content').innerHTML=Object.entries(plan.rows).map(([name,row])=>`<h3>${{original_id:plan.original_journal_ids?'Original expense — selected journals':'Original expense',new_id:'New charge',refund_id:'Refund deposit'}[name]}</h3>${name==='refund_id'?gbitRefundCard(row,plan.refund_original):duplicateCard(row)}`).join('')+`<p>Original expense → new charge: <strong>${esc(plan.link_names?.GBIT||'GBIT')}</strong>.</p>${plan.rows.refund_id?`<p>Refund deposit → original expense (deposit refunds expense): <strong>${esc(plan.link_names?.['GBIT Refund']||'GBIT Refund')}</strong>.</p><p>GBIT tags are removed only after both link types are verified. Verification also repairs reversed GBIT Refund links created by Sidecar for these exact journals. Other conflicting links require manual inspection.</p>`:'<p>Only the GBIT charge link will be created. Tags remain until the refund is matched.</p>'}<p>${plan.links.length} journal links will be verified. Existing matching links are reused.</p>`;
  $('gbit-dialog').showModal();
}
$('load-gbit').addEventListener('click',()=>perform(loadGbit));
$('gbit-new').addEventListener('change',renderGbitDetails);
$('gbit-original').addEventListener('change',renderGbitDetails);
$('gbit-original-journals').addEventListener('change',event=>{
  const id=event.target.dataset.gbitJournal;
  if(!id||busy)return;
  if(event.target.checked)gbitOriginalJournals.add(id);else gbitOriginalJournals.delete(id);
  renderGbitDetails();
});
$('gbit-refund-journals').addEventListener('change',event=>{
  const id=event.target.dataset.gbitRefundJournal;if(!id||busy)return;
  if(event.target.checked)gbitRefundJournals.add(id);else gbitRefundJournals.delete(id);
  renderGbitDetails();
});
$('gbit-refund').addEventListener('change',renderGbitDetails);
$('gbit-search').addEventListener('input',renderGbitOriginals);
$('gbit-selected').addEventListener('click',()=>perform(()=>flagGbit([...validationSelected])));
$('review-gbit').addEventListener('click',()=>perform(async()=>showGbitReview(await api('/api/gbit/review',{original_id:$('gbit-original').value,original_journal_ids:[...gbitOriginalJournals],refund_original_journal_ids:[...gbitRefundJournals],new_id:$('gbit-new').value,refund_id:$('gbit-refund').value}))));
$('gbit-operations').addEventListener('click',event=>{
  const continuation=event.target.closest('[data-continue-gbit]');
  if(continuation&&!busy) {
    const op=gbitData.operations.find(item=>item.plan.id===continuation.dataset.continueGbit);
    if(!op)return;
    const rows=op.plan.rows;
    if(!gbitData.new_expenses.some(row=>row.group_id===rows.new_id.group_id))gbitData.new_expenses.push(rows.new_id);
    if(!gbitData.originals.some(row=>row.group_id===rows.original_id.group_id)) {
      const splits=op.plan.groups?.original_id?.attributes.transactions;
      gbitData.originals.push(splits?{...rows.original_id,journal_count:splits.length,
        splits:splits.map(split=>({journal_id:String(split.transaction_journal_id),description:split.description,amount:split.amount,source:split.source_name,destination:split.destination_name})),
        total:decimal(splits.reduce((sum,split)=>sum+units(split.amount),0n))}:rows.original_id);
    }
    gbitOptions('gbit-new',gbitData.new_expenses,'Select a pending GBIT withdrawal…');
    $('gbit-new').value=rows.new_id.group_id;
    $('gbit-search').value='';renderGbitOriginals();
    $('gbit-original').value=rows.original_id.group_id;
    gbitOriginalGroup=rows.original_id.group_id;
    gbitOriginalJournals=new Set(op.plan.original_journal_ids||rows.original_id.splits.map(row=>row.journal_id));
    gbitRefundJournals=new Set(op.plan.refund_original_journal_ids||[]);
    $('gbit-refund').value='';renderGbitDetails();
    $('gbit-refund').scrollIntoView?.({behavior:'smooth',block:'center'});$('gbit-refund').focus?.();
    return;
  }
  const button=event.target.closest('[data-resume-gbit]');if(!button||busy)return;
  const op=gbitData.operations.find(op=>op.plan.id===button.dataset.resumeGbit);if(op)showGbitReview(op.plan);
});
$('cancel-gbit').addEventListener('click',()=>$('gbit-dialog').close());
$('gbit-dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault();});
$('apply-gbit').addEventListener('click',()=>perform(async()=>{
  let result;
  try {result=await api('/api/gbit/apply',{plan_id:gbitPlan.id});}
  catch(error){$('gbit-review-status').textContent=error.message;throw error;}
  $('gbit-dialog').close();
  autoLoadedTools.delete('validation');autoLoadedTools.delete('duplicates');autoLoadedTools.delete('reimbursements');
  autoLoadedTools.delete('gbit');
  if($('history').hidden===false)await loadActivity();else await loadGbit();
  notice(result.complete?'GBIT complete: both link types verified and GBIT tags removed.':result.awaiting_refund?'New charge linked. GBIT remains tagged and incomplete until the refund is matched.':'GBIT paused: '+result.error+' Open the saved operation to inspect and resume.',result.complete||result.awaiting_refund);
}));

let categorizeSession,categorizeIds=[];
const categorizeFields={source_id:'categorize-source',destination_id:'categorize-destination',category_id:'categorize-category',budget_id:'categorize-budget',bill_id:'categorize-bill'};
function categorizationChanges() {
  const changes={};
  for(const [field,id] of Object.entries(categorizeFields)) {
    const value=$(id).value;
    if(value&&value!=='keep')changes[field]=value==='clear'?null:value;
  }
  if($('categorize-description-mode').value==='set')changes.description=$('categorize-description').value;
  return changes;
}
function categorizeControls() {
  $('categorize-description-mode').disabled=busy;
  $('categorize-description').disabled=busy||$('categorize-description-mode').value!=='set';
  const withdrawals=categorizeSession?.transactions.some(row=>categorizeIds.includes(row.journal_id)&&row.type==='withdrawal');
  $('categorize-budget').disabled=busy||!withdrawals;
  $('categorize-bill').disabled=busy||!withdrawals;
  $('apply-categorize').disabled=busy||!categorizeSession||!categorizeIds.length||!Object.keys(categorizationChanges()).length;
}
function categorizeOptions(id,options,clear=false) {
  $(id).innerHTML='<option value="keep">Keep unchanged</option>'+(clear?'<option value="clear">Clear assignment</option>':'')+options.map(option=>`<option value="${esc(option.id)}">${esc(option.name)}${option.type?' ('+esc(option.type)+')':''}</option>`).join('');
  $(id).value='keep';
}
async function openCategorize(ids) {
  categorizeSession=undefined;categorizeIds=[...new Set(ids)];
  $('categorize-description-mode').value='keep';$('categorize-description').value='';
  $('categorize-status').textContent='Loading current transactions and choices from Firefly…';
  $('categorize-targets').innerHTML='';
  for(const id of Object.values(categorizeFields))categorizeOptions(id,[]);
  $('categorize-dialog').showModal();
  try {
    categorizeSession=await api('/api/validation/categorize-options',{journal_ids:categorizeIds});
    if(categorizeIds.length===1)$('categorize-description').value=categorizeSession.transactions.find(row=>row.journal_id===categorizeIds[0])?.description||'';
    for(const [field,id] of [['source_id','categorize-source'],['destination_id','categorize-destination']]) {
      const allowed=categorizeSession.accounts.filter(account=>categorizeSession.transactions.every(row=>row.allowed_accounts[field].includes(account.id)));
      categorizeOptions(id,allowed);
    }
    categorizeOptions('categorize-category',categorizeSession.categories,true);
    categorizeOptions('categorize-budget',categorizeSession.budgets,true);
    categorizeOptions('categorize-bill',categorizeSession.bills,true);
    $('categorize-target-count').textContent=`${categorizeIds.length} selected transaction journal${categorizeIds.length===1?'':'s'}`;
    $('categorize-targets').innerHTML=categorizeSession.transactions.map(row=>`<p>${fireflyLink(row.group_id,row.description)} · ${esc(transactionIdLabel(row))}<br>${esc(row.source_name)} → ${esc(row.destination_name)} · ${esc(fmt(row.amount,row.currency_code))}<br>Category: ${esc(row.category_name||'None')} · Budget: ${esc(row.budget_name||'None')} · Subscription: ${esc(row.bill_name||'None')}</p>`).join('');
    $('categorize-help').textContent='Account choices are valid for every selected transaction type. For mixed types, categorize accounts separately if no common choice exists. Budget and subscription changes affect withdrawals only.';
    $('categorize-status').textContent='Choose fields to change, then apply.';
    categorizeControls();
  }catch(error){$('categorize-status').textContent=error.message;throw error;}
}
$('categorize-selected').addEventListener('click',()=>perform(()=>openCategorize([...validationSelected])));
for(const id of Object.values(categorizeFields))$(id).addEventListener('change',categorizeControls);
$('categorize-description-mode').addEventListener('change',categorizeControls);
$('categorize-description').addEventListener('input',categorizeControls);
$('cancel-categorize').addEventListener('click',()=>{$('categorize-dialog').close();categorizeSession=undefined;});
$('categorize-dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault();else categorizeSession=undefined;});
$('apply-categorize').addEventListener('click',()=>perform(async()=>{
  const changes=categorizationChanges();
  if(!categorizeSession||!Object.keys(changes).length)throw new Error('Choose at least one field to change.');
  const failures=[];let completed=0;
  for(const jid of [...categorizeIds]) {
    $('categorize-status').textContent=`Applying changes: ${completed+failures.length+1} of ${categorizeIds.length}…`;
    try {await api('/api/validation/categorize',{token:categorizeSession.token,journal_id:jid,changes});validationSelected.delete(jid);completed++;}
    catch(error){failures.push({jid,error:error.message});}
  }
  categorizeIds=failures.map(item=>item.jid);
  autoLoadedTools.delete('gbit');autoLoadedTools.delete('duplicates');autoLoadedTools.delete('reimbursements');
  let reloadError='';
  try {await loadValidation();}catch(error){reloadError=' Reload the review queue: '+error.message;}
  if(failures.length) {
    $('categorize-status').textContent=`${completed} updated. Failed transactions remain selected in this dialog.\n`+failures.map(item=>`${transactionIdLabel(categorizeSession.transactions.find(row=>row.journal_id===item.jid)||{journal_id:item.jid})}: ${item.error}`).join('\n')+reloadError;
    categorizeControls();
  }else {
    $('categorize-dialog').close();categorizeSession=undefined;
    notice(`${completed} transaction journal${completed===1?'':'s'} categorized. Tags kept.${reloadError}`,!reloadError);
  }
}));

let reimbursementSession,splitDescriptionBeforeReimbursement;
function reimbursementControls() {
  const row=reimbursementSession?.transaction;
  const value=Number($('reimbursement-value').value),total=Number(row?.amount);
  const percent=$('reimbursement-mode').value==='percent';
  const precision=Number(row?.currency_decimal_places??2);
  const scale=10**precision;
  const amount=percent?Math.round(total*value/100*scale)/scale:value;
  const reimburse=$('split-reimbursement').checked;
  $('split-reimbursement').disabled=busy;$('split-description').disabled=busy||reimburse;
  $('reimbursement-help').textContent=reimburse?`Reimbursement uses cash settings, adds ${config?.tag||'Reimburse'}, and validates every split in the transaction.`:'Both portions keep their accounts, category, budget, subscription and tags. The transaction stays in its current validation state.';
  const valid=!!row&&(reimburse||amount<total)&&!!(reimburse||$('split-description').value.trim())&&Number.isFinite(value)&&value>0&&value<=(percent?100:total)&&amount>0&&amount<=total;
  $('reimbursement-value').max=percent?'100':row?.amount||'';
  $('reimbursement-value').step=percent?'any':String(1/scale);
  $('confirm-reimbursement').disabled=busy||!valid;
  $('confirm-reimbursement').textContent=reimburse?'Mark as Reimbursement':'Split transaction';
  $('reimbursement-preview').textContent=valid?`${fmt(amount,row.currency_code)} selected · ${fmt(total-amount,row.currency_code)} remaining${amount===total?' · Full reimbursement; description kept.':` · New split: ${reimburse?'Reimbursement':$('split-description').value}.`}`:'Enter a positive amount that leaves a remainder, or select reimbursement to allow 100%.';

}
async function openReimbursement(jid) {
  reimbursementSession=undefined;splitDescriptionBeforeReimbursement=undefined;
  $('reimbursement-target').innerHTML='';
  $('reimbursement-status').textContent='Loading current transaction…';
  $('reimbursement-mode').value='percent';$('reimbursement-value').value='50';$('split-reimbursement').checked=false;$('split-description').value='';
  $('reimbursement-dialog').showModal();
  try {
    reimbursementSession=await api('/api/validation/split-options',{journal_id:jid});
    const row=reimbursementSession.transaction;
    $('split-description').value=row.description;
    $('reimbursement-target').innerHTML=`${fireflyLink(row.group_id,row.description)} · ${esc(transactionIdLabel(row))} · ${esc(fmt(row.amount,row.currency_code))}`;
    $('reimbursement-help').textContent=`The reimbursable portion is marked as cash: category, budget and subscription cleared; transfers keep both accounts. Adds ${config.tag}. Removes the todo tag from every split, validating the whole transaction. Other split details are kept.`;
    $('reimbursement-status').textContent='Choose a percentage or amount, then apply.';
  } catch(error) {$('reimbursement-status').textContent=error.message;throw error;}
  reimbursementControls();
}
for(const id of ['reimbursement-mode','reimbursement-value','split-description','split-reimbursement'])$(id).addEventListener('input',reimbursementControls);
$('split-reimbursement').addEventListener('change',()=>{
  if($('split-reimbursement').checked) {
    splitDescriptionBeforeReimbursement=$('split-description').value;
    $('split-description').value='Reimbursement';
  } else {
    $('split-description').value=splitDescriptionBeforeReimbursement??reimbursementSession?.transaction.description??'';
  }
  reimbursementControls();
});
$('cancel-reimbursement').addEventListener('click',()=>{$('reimbursement-dialog').close();reimbursementSession=undefined;});
$('reimbursement-dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault();else reimbursementSession=undefined;});
$('confirm-reimbursement').addEventListener('click',()=>perform(async()=>{
  if(!reimbursementSession)throw new Error('Open a new split preview.');
  const token=reimbursementSession.token;
  $('reimbursement-status').textContent='Applying and verifying split…';
  try {
    await api('/api/validation/split',{token,reimbursement:$('split-reimbursement').checked,description:$('split-description').value,mode:$('reimbursement-mode').value,value:$('reimbursement-value').value});
    reimbursementSession=undefined;$('reimbursement-dialog').close();
    try {await loadValidation();notice('Transaction split saved and totals verified.',true);}
    catch(error){notice('Transaction split saved. Could not refresh transaction review: '+error.message);}
  }catch(error){
    reimbursementSession=undefined;
    $('reimbursement-status').textContent=error.message+' Inspect the transaction and Activity, then reopen this dialog before trying again.';
    throw error;
  }
}));


let consistencyQuery,consistencyNext=null,consistencyResult;
const consistencyFilterIds=['consistency-start','consistency-end','consistency-type','consistency-rule','consistency-account','consistency-tag','consistency-group','consistency-limit'];
for(const id of consistencyFilterIds)$(id).addEventListener('change',()=>{
  consistencyNext=null;consistencyResult=undefined;$('next-consistency').disabled=true;
  $('consistency-summary').textContent='Filters changed. Run a new check.';
  $('consistency-results').innerHTML='';
});
async function scanConsistency(page=1) {
  if(page===1)consistencyQuery={start:$('consistency-start').value,end:$('consistency-end').value,
    type:$('consistency-type').value||'all',rule:$('consistency-rule').value||'all',
    account_id:$('consistency-account').value.trim(),tag:$('consistency-tag').value.trim(),
    group_id:$('consistency-group').value.trim(),limit:$('consistency-limit').value||'25'};
  $('next-consistency').disabled=true;$('scan-consistency').disabled=true;
  for(const id of consistencyFilterIds)$(id).disabled=true;
  $('consistency-summary').textContent='Checking one page of journals and their links…';
  try {
    const result=await api('/api/consistency?'+new URLSearchParams({...consistencyQuery,page}));
    consistencyNext=result.next_page;
    $('consistency-summary').textContent=`Page ${result.page} · ${result.groups} parents loaded · ${result.checked} journals checked · ${result.applicable} require cash settings · ${result.findings.length} inconsistent · ${result.errors.length} incomplete checks. ${result.next_page?'More pages are available; check the next page explicitly.':'End of this filtered result.'}`;
    consistencyResult=result;renderConsistencyResults();
  } catch(error) {
    consistencyNext=null;consistencyResult=undefined;$('consistency-summary').textContent='Check failed: '+error.message;
    $('consistency-results').innerHTML='';throw error;
  } finally {for(const id of consistencyFilterIds)$(id).disabled=false;$('scan-consistency').disabled=false;$('next-consistency').disabled=consistencyNext===null;}
}
$('consistency-filters').addEventListener('submit',event=>{event.preventDefault();return perform(()=>scanConsistency());});
$('next-consistency').addEventListener('click',()=>perform(()=>scanConsistency(consistencyNext)));

function renderConsistencyResults() {
  if(!consistencyResult)return;
  const result=consistencyResult,all=$('consistency-show').value==='all';
  const rows=all?(result.evaluated||result.findings):result.findings;
  $('consistency-results').innerHTML=rows.map(row=>`<article class="card history-card"><div class="history-heading"><strong>${fireflyLink(row.group_id,`#${row.group_id} · ${row.description}`)}</strong><span class="status">${esc({consistent:'Consistent',inconsistent:'Inconsistent',incomplete:'Check incomplete',not_applicable:'No applicable rule'}[row.status]||'Inconsistent')}</span></div><p>${esc(transactionIdLabel(row))} · ${esc(date(row.date))} · ${esc(fmt(row.amount,row.currency_code))}</p><p>${esc(row.source_name)} → ${esc(row.destination_name)}</p><p>${row.reasons.map(esc).join(' · ')}</p>${row.issues.length?`<ul>${row.issues.map(issue=>`<li>${esc(issue)}</li>`).join('')}</ul>`:''}${(row.check_errors||[]).map(error=>`<p>Check incomplete: ${esc(error)}</p>`).join('')}</article>`).join('')+(!all||!result.evaluated?result.errors.map(row=>`<article class="card history-card"><strong>${fireflyLink(row.group_id,'#'+row.group_id)}</strong><p>${esc(transactionIdLabel(row))} · Check incomplete: ${esc(row.error)}</p></article>`).join(''):'')||`<div class="card empty">${all?'No journals evaluated on this page.':'No cash-rule mismatches found on this page.'}</div>`;
}
$('consistency-show').addEventListener('change',renderConsistencyResults);
