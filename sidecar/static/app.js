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
  const r = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Sidecar-CSRF':config.csrf},body:JSON.stringify(body)});
  const json = await r.json();
  if (!r.ok) throw new Error(json.error || 'Request failed.');
  return json;
}
function currentDeposit() { return data.deposits.find(x => x.journal_id === $('deposit').value); }
function selection() { return data.expenses.filter(x => selected.has(x.journal_id)); }
function setBusy(value) {
  busy=value;
  for(const id of ['filter-dates','review','apply','test-connection','cancel-review','load-validation','load-duplicates','cancel-delete','confirm-delete','more-activity','more-duplicates','load-refund','confirm-refund','cancel-refund','refund-start','refund-end','refund-tolerance','refund-remove-todo','refund-same-account','load-gbit','apply-gbit','cancel-gbit','gbit-new','gbit-original','gbit-refund','gbit-start','gbit-end','gbit-search','cancel-categorize','categorize-source','categorize-destination','categorize-category','categorize-budget','categorize-bill']) $(id).disabled=value;
  $('deposit').disabled=value || !loaded;
  renderExpenses();
  renderValidation();
  renderGbitDetails();
  categorizeControls();
  $('confirm-refund').disabled=value||!refundSelection;
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
    return `<tr class="${selected.has(x.journal_id)?'selected ':''}${disabled?'unavailable':''}"><td><input type="checkbox" aria-label="Select ${esc(x.group_title||x.destination_name)} reimbursement ${esc(x.journal_id)}" data-journal="${esc(x.journal_id)}" ${selected.has(x.journal_id)?'checked':''} ${disabled||busy?'disabled':''}></td><td><strong>${fireflyLink(x.group_id,x.group_title||x.destination_name||x.description)}</strong><small>${esc(x.description)} · ${esc(x.destination_name)} · Journal #${esc(x.journal_id)}</small></td><td><div class="row-tags">${(x.tags||[]).map(tag=>`<span class="tag">${esc(tag.startsWith('#')?tag:'#'+tag)}</span>`).join('') || '—'}</div></td><td>${esc(date(x.date))}</td><td>${esc(x.source_name)}</td><td class="right"><strong>${esc(fmt(x.amount,x.currency_code))}</strong>${disabled?'<small>Different currency</small>':''}</td></tr>`;
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
  $('review-content').innerHTML=`<div class="review-deposit"><strong>${fireflyLink(d.group_id,d.description)}</strong><p>${esc(date(d.date))} · ${esc(d.source_name)} · Deposit #${esc(d.transaction_journal_id)}</p><strong>${esc(fmt(d.amount,p.currency))}</strong></div>`+p.expenses.map(x=>`<div class="review-line"><div>${fireflyLink(x.group_id,x.group_title||x.destination_name)}<br><small>Reimbursement journal #${esc(x.journal_id)}</small></div><strong>${esc(fmt(x.amount,x.currency_code))}</strong></div>`).join('')+`<div class="review-line review-total"><span>Selected reimbursement total</span><span>${esc(fmt(p.total,p.currency))}</span></div>${differenceWarning(d.amount,p.total,p.currency)?`<p class="match-warning" role="status">${esc(differenceWarning(d.amount,p.total,p.currency))}</p>`:''}<p class="review-note">Expense split <b>${esc(p.link_type.inward)}</b> deposit.<br>Each verified link is followed by removal of the <b>${esc(p.tag)}</b> tag from that expense split. Other tags are preserved.</p>`;
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
  $('history-list').innerHTML=rows.map(x=>`<article class="card history-card"><div class="history-heading"><strong>${fireflyLink(x.plan.deposit.group_id,x.plan.deposit.description)} · ${esc(fmt(x.plan.total,x.plan.currency))}</strong><span class="status">${esc(x.state)}</span></div><p>${activityTimestamp(x.created)} · ${x.plan.expenses.length===1?'Journal #'+esc(x.plan.expenses[0].journal_id):x.plan.expenses.length+' journals'} · Deposit #${esc(x.plan.deposit.transaction_journal_id)}</p><p>${x.plan.expenses.map(e=>fireflyLink(e.group_id,'Journal #'+e.journal_id)).join(' · ')}</p><ul>${(x.result?.items||[]).map(i=>`<li>Journal #${esc(i.journal_id)}: ${esc(i.status)}${i.error?' — '+esc(i.error):''}</li>`).join('')}</ul>${x.state!=='complete'?`<button class="secondary" data-resume="${esc(x.id)}">${x.state==='review'?'Open review':'Inspect & resume'}</button>`:''}</article>`).join('')||'<div class="card empty">Your reimbursement activity will appear here.</div>';
  $('history-list').querySelectorAll('[data-resume]').forEach(button=>button.addEventListener('click',()=>perform(async()=>renderPlan(rows.find(x=>x.id===button.dataset.resume).plan))));
}
const autoLoadedTools=new Set();
async function view(name) {
  document.querySelectorAll('.view').forEach(x=>x.hidden=x.id!==name);
  document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.view===name));
  $('breadcrumb').textContent={validation:'Transaction review',reimbursements:'Reimbursements',duplicates:'Duplicate checker',gbit:'GBITs',history:'Activity',connection:'Connection'}[name];
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
    $('matching-rules').textContent=`Pending tag: ${config.tag}. All uncategorized withdrawals carrying this tag are included, regardless of description. Change the tag using REIMBURSE_TAG.`;
    if(!config.configured){await view('connection');notice('Add your Firefly III URL and API token to the Docker environment to get started.');return;}
    $('todo-tag').textContent=config.todo_tag;
    renderStats(); renderExpenses();
    await perform(()=>view('validation'));
  } catch(e) { notice(e.message); }
})();

let validationRows=[], validationLoaded=false, validationSelected=new Set();
function visibleValidationRows() {
  const q=$('validation-search').value.toLowerCase();
  return validationRows.filter(x=>[x.group_title,x.description,x.source_name,x.destination_name,x.category_name,...(x.tags||[])].join(' ').toLowerCase().includes(q));
}
function renderValidation() {
  validationSelected=new Set([...validationSelected].filter(id=>validationRows.some(row=>row.journal_id===id)));
  const rows=visibleValidationRows();
  $('validation-rows').innerHTML=rows.map(x=>`<tr class="${validationSelected.has(x.journal_id)?'selected':''}"><td><input type="checkbox" data-review-select="${esc(x.journal_id)}" aria-label="Select journal ${esc(x.journal_id)}" ${validationSelected.has(x.journal_id)?'checked':''} ${busy?'disabled':''}></td><td><strong>${fireflyLink(x.group_id,x.description)}</strong><small>${esc(x.group_title)} · Journal #${esc(x.journal_id)}</small><small>Accounts: ${esc(x.source_name)} → ${esc(x.destination_name)}</small><small>Category: ${esc(x.category_name||'Uncategorized')}</small><small>Tags: ${(x.tags||[]).map(esc).join(' · ')||'None'}</small></td><td>${esc(date(x.date))}</td><td class="right">${esc(fmt(x.amount,x.currency_code))}</td><td>${reviewDuplicateStatus(x.duplicate_check)}</td><td><div class="row-actions">${reviewAction('validate',x.journal_id,'Mark validated')}${reviewAction('categorize',x.journal_id,'Categorize')}${reviewAction('cash',x.journal_id,'Mark as cash')}${['withdrawal','deposit'].includes(x.type)?reviewAction('gbit',x.journal_id,'Mark as GBIT'):''}${x.type==='deposit'?reviewAction('refund',x.journal_id,'Mark as Refund'):''}${deleteButton(x.group_id)}</div></td></tr>`).join('')||`<tr><td colspan="6" class="empty">${validationLoaded?'No transactions match.':'Click Load from Firefly to see transactions awaiting validation.'}</td></tr>`;
  $('validation-count').textContent=validationLoaded?`${rows.length} of ${validationRows.length} awaiting validation`:'Not loaded';
  const visibleSelected=rows.filter(row=>validationSelected.has(row.journal_id)).length;
  $('validation-select-all').checked=rows.length>0&&visibleSelected===rows.length;
  $('validation-select-all').indeterminate=visibleSelected>0&&visibleSelected<rows.length;
  $('validation-select-all').disabled=busy||!rows.length;
  $('validation-selection-count').textContent=`${validationSelected.size} selected (${visibleSelected} visible)`;
  $('validate-selected').disabled=busy||!validationSelected.size;
  $('cash-selected').disabled=busy||!validationSelected.size;
  $('gbit-selected').disabled=busy||!validationSelected.size;
  $('categorize-selected').disabled=busy||!validationSelected.size;
  $('clear-validation-selection').disabled=busy||!validationSelected.size;
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
  const categorize=event.target.closest('[data-categorize]');
  if(categorize){perform(()=>openCategorize([categorize.dataset.categorize]));return;}
  const gbit=event.target.closest('[data-gbit]');
  if(gbit){perform(()=>flagGbit([gbit.dataset.gbit]));return;}
  const refund=event.target.closest('[data-refund]');
  if(refund){perform(()=>openRefund(refund.dataset.refund));return;}
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
function transactionJournalDetails(row) {
  const journalLine=s=>`<div class="review-line"><div>${esc(s.description)}<small>Journal #${esc(s.journal_id)} · ${esc(s.source)} → ${esc(s.destination)}</small></div><strong>${esc(fmt(s.amount,row.currency))}</strong></div>`;
  if(row.splits.length===1)return journalLine(row.splits[0]);
  if(!row.splits.length)return '';
  return `<details><summary>${row.splits.length} journals · Split breakdown</summary>${row.splits.map(journalLine).join('')}</details>`;
}
function duplicateCard(row, deletable=false) {
  return `<article class="duplicate-transaction"><h3>${fireflyLink(row.group_id,row.title)}</h3>${deletable?deleteButton(row.group_id):''}<p>${esc(row.date)} · ${esc(row.type)} · Transaction #${esc(row.group_id)}</p><strong>${esc(fmt(row.total,row.currency))}</strong><p>${row.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join(' ')||'No tags'}</p>${transactionJournalDetails(row)}</article>`;
}
let duplicatePairs=[],duplicateNext=null,duplicateQuery;
async function loadDuplicates(append=false) {
  const start=$('duplicates-start').value,end=$('duplicates-end').value,days=$('duplicates-days').value;
  if(!append&&(!start||!end||start>end)) throw new Error('Choose a valid duplicate-check date range.');
  if(!append&&(!/^\d+$/.test(days)||Number(days)>31)) throw new Error('Days apart must be a whole number between 0 and 31.');
  notice('Checking transaction totals for duplicates…');
  const query=append?{...duplicateQuery,offset:duplicateNext}:{start,end,days};
  const result=await api('/api/duplicates?'+new URLSearchParams(query));
  if(!append)duplicateQuery={start,end,days};
  duplicatePairs=append?duplicatePairs.concat(result.pairs):result.pairs;
  duplicateNext=result.next_offset??null;
  $('more-duplicates').hidden=duplicateNext===null;
  $('duplicates-summary').textContent=`${result.scanned} transactions scanned · ${duplicatePairs.length} candidate pairs shown${duplicateNext!==null?' (more available below)':' (all loaded)'} · ${result.skipped.length} needing manual review`;
  $('duplicates-results').innerHTML=duplicatePairs.map(pair=>`<section class="card duplicate-pair"><div class="duplicate-heading">Same total, currency, type and account · ${pair.days_apart} day${pair.days_apart===1?'':'s'} apart${pair.signals.length?' · '+esc(pair.signals.join(' · ')):''}</div><div class="duplicate-columns">${duplicateCard(pair.left)}${duplicateCard(pair.right)}</div></section>`).join('')||'<div class="card empty">No duplicate candidates found in this range.</div>';
  $('duplicates-skipped').hidden=!result.skipped.length;
  $('duplicates-skipped-list').innerHTML=result.skipped.map(row=>`<p>${fireflyLink(row.group_id,row.title)}: ${esc(row.reason)}</p>`).join('');
  notice(duplicateNext!==null?'More duplicate candidates are available. Click Load more candidates below the results.':'All duplicate candidates loaded. Candidates require manual review.',duplicateNext===null);
}
$('load-duplicates').addEventListener('click',()=>perform(()=>loadDuplicates()));
$('more-duplicates').addEventListener('click',()=>perform(()=>loadDuplicates(true)));

function reviewDuplicateStatus(check) {
  if(!check) return '<span class="muted">Not checked</span>';
  if(check.status!=='checked') return `<span class="duplicate-alert">${check.status==='manual'?'Manual review needed':'Check unavailable'}</span><small>${esc(check.reason)}</small>`;
  if(!check.match_count) return `<span class="muted">No candidates within ±${check.days} days</span>`;
  return `<details class="review-duplicates"><summary class="duplicate-alert">${check.match_count} potential duplicate${check.match_count===1?'':'s'}</summary><p>Same parent total, currency, type and account. Review before validating.</p>${check.matches.map(match=>`<div class="review-duplicate-match"><p>${match.days_apart} days apart${match.signals.length?' · '+esc(match.signals.join(' · ')):''}</p>${duplicateCard(match.transaction,true)}</div>`).join('')}${check.truncated?'<p>Showing the first 20 matches.</p>':''}</details>`;
}

let deletionPreview;
function reviewAction(action,id,label) {
  const paths={
    validate:'<path d="m5 12 4 4L19 6"/>',
    categorize:'<path d="M20 13 11 22 2 13V4h9l9 9Z" transform="translate(1 -1) scale(.9)"/><circle cx="7" cy="7" r="1"/>',
    cash:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M16 10h5v5h-5a2.5 2.5 0 0 1 0-5Z"/><path d="M6 5V3h12"/>',
    gbit:'<path d="M3 10a9 9 0 1 1 2 8M3 4v6h6M12 7v5l3 2"/>',
    refund:'<path d="m9 4-6 6 6 6M3 10h11a6 6 0 0 1 0 12" transform="translate(1 -1) scale(.9)"/>',
    delete:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>'
  };
  return `<button type="button" class="icon-action ${action==='delete'?'danger-icon':action==='validate'?'success-icon':''}" data-${action}="${esc(id)}" title="${esc(label)}" aria-label="${esc(label)}" ${busy?'disabled':''}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths[action]||''}</svg></button>`;
}
function deleteButton(groupId) {return reviewAction('delete',groupId,'Delete transaction');}
async function previewDelete(groupId) {
  deletionPreview=await api('/api/validation/delete-preview',{group_id:groupId});
  const group=deletionPreview.transaction, splits=group.attributes.transactions;
  $('delete-content').innerHTML=`<h3>${fireflyLink(deletionPreview.group_id,group.attributes.group_title||splits[0]?.description||'Transaction')}</h3><p>Transaction #${esc(deletionPreview.group_id)} · ${splits.length===1?'The transaction will be deleted.':splits.length+' journals will be deleted.'}</p>`+splits.map(s=>`<div class="review-line"><div>${esc(s.description)}<small>#${esc(s.transaction_journal_id)} · ${esc(date(s.date))} · ${esc(s.source_name)} → ${esc(s.destination_name)}</small><p>${(s.tags||[]).map(esc).join(' · ')}</p></div><strong>${esc(fmt(s.amount,s.currency_code))}</strong></div>`).join('');
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
  $('activity-list').innerHTML=activityEvents.map(event=>`<article class="card history-card"><div class="history-heading"><strong>${esc(event.action)}</strong><span class="status">${esc(event.state)}</span></div><p>${activityTimestamp(event.created)} · ${esc(event.method)} ${esc(event.path)}</p>${event.group_id?`<p>${fireflyLink(event.group_id,'Transaction #'+event.group_id)}${event.method==='DELETE'?' (may no longer exist in Firefly)':''}</p>`:''}${(event.tag_changes||[]).map(change=>`<p>Journal #${esc(change.journal_id)}: ${esc(change.before.join(', ')||'No tags')} → ${esc(change.after.join(', ')||'No tags')}</p>`).join('')}${event.error?`<p class="duplicate-alert">${esc(event.error)}</p>`:''}${event.verification_note?`<p>${esc(event.verification_note)}</p>`:''}<details><summary>Request and transaction snapshots</summary><pre class="audit-json">${esc(JSON.stringify({request:event.request,before:event.before,after:event.after,response:event.response},null,2))}</pre></details></article>`).join('')||'<div class="card empty">No recorded Firefly changes yet.</div>';
  $('more-activity').hidden=activityOffset===null;
}
$('more-activity').addEventListener('click',()=>perform(()=>loadActivity(true)));

$('validation-rows').addEventListener('change',event=>{
  const id=event.target.dataset.reviewSelect;
  if(!id||busy)return;
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
    } catch(error) {failures.push(`Journal #${id}: ${error.message}`);}
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
      validationSelected.delete(id);completed++;
    } catch(error) {failures.push(`Journal #${id}: ${error.message}`);}
  }
  autoLoadedTools.delete('duplicates');autoLoadedTools.delete('reimbursements');
  let reloadError='';
  try {await loadValidation();}catch(error){reloadError=`\nChanges may have completed. Reload the queue: ${error.message}`;}
  notice(`${completed} transaction${completed===1?'':'s'} marked as cash. Todo and other tags are kept.${failures.length?'\n'+failures.join('\n'):''}${reloadError}`,!failures.length&&!reloadError);
}
$('cash-selected').addEventListener('click',()=>perform(()=>markCash([...validationSelected])));

let refundDepositId,refundSearch,refundSelection;
async function openRefund(id) {
  refundDepositId=id;refundSearch=undefined;refundSelection=undefined;
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
  refundSearch=undefined;refundSelection=undefined;$('confirm-refund').disabled=true;
  let result;
  try {result=await api('/api/validation/refund-candidates',body);}
  catch(error){$('refund-status').textContent=error.message;throw error;}
  refundSearch=result;
  $('refund-same-account').checked=result.same_account;
  $('refund-start').value=result.start;$('refund-end').value=result.end;$('refund-tolerance').value=result.tolerance;
  $('refund-deposit').innerHTML=`${fireflyLink(result.deposit.group_id,result.deposit.description)} · ${esc(fmt(result.deposit.amount,result.deposit.currency_code))} · ${esc(date(result.deposit.date))}`;
  $('refund-candidates').innerHTML=result.candidates.map(row=>`<div class="card refund-option"><label><input type="radio" name="refund-withdrawal" value="${esc(row.group_id)}"> Select transaction #${esc(row.group_id)}</label>${refundWithdrawalCard(row)}<p>Difference from deposit: ${esc(fmt(row.difference,row.currency))}</p></div>`).join('')||'<p>No withdrawals match these dates and amount tolerance.</p>';
  $('refund-status').textContent=`${result.candidates.length} candidates. ${result.skipped.length} unsupported groups excluded (mixed currencies/accounts/dates or invalid amounts).`;
}
$('load-refund').addEventListener('click',()=>perform(()=>searchRefund()));
$('refund-candidates').addEventListener('change',event=>{
  if(busy||event.target.name!=='refund-withdrawal')return;
  refundSelection=event.target.value;$('confirm-refund').disabled=false;
});
$('cancel-refund').addEventListener('click',()=>{$('refund-dialog').close();refundSelection=undefined;});
$('refund-dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault();});
$('confirm-refund').addEventListener('click',()=>perform(async()=>{
  if(!refundSearch||!refundSelection)throw new Error('Choose a withdrawal first.');
  $('refund-status').textContent='Creating and verifying Refund links…';
  try {
    const result=await api('/api/validation/mark-refund',{token:refundSearch.token,group_id:refundSelection,remove_todo:$('refund-remove-todo').checked});
    $('refund-dialog').close();refundSelection=undefined;
    autoLoadedTools.delete('duplicates');autoLoadedTools.delete('reimbursements');
    try {await loadValidation();notice(`Refund linked (${result.links} journal links) and both transactions marked as cash.${result.todo_removed?' Todo tag removed.':' Todo tag kept.'}`,true);}
    catch(error){notice(`Refund links created. Reload the queue: ${error.message}`);}
  } catch(error) {$('refund-status').textContent=error.message+' Some links may exist already; inspect Activity or retry this selection.';throw error;}
}));

function refundWithdrawalCard(row) { return duplicateCard(row); }
$('refund-same-account').addEventListener('change',()=>{if(!busy)perform(()=>searchRefund());});

let gbitData={new_expenses:[],refunds:[],originals:[],operations:[]},gbitPlan;
function gbitSelected() {
  return {new_id:gbitData.new_expenses.find(r=>r.group_id===$('gbit-new').value),
          original_id:gbitData.originals.find(r=>r.group_id===$('gbit-original').value),
          refund_id:gbitData.refunds.find(r=>r.group_id===$('gbit-refund').value)};
}
function gbitOptions(id,rows,placeholder) {
  const before=$(id).value;
  $(id).innerHTML=`<option value="">${esc(placeholder)}</option>`+rows.map(row=>`<option value="${esc(row.group_id)}">${esc(row.date)} · ${esc(row.title)} · ${esc(fmt(row.total,row.currency))} · #${esc(row.group_id)}</option>`).join('');
  if(rows.some(row=>row.group_id===before))$(id).value=before;
}
function renderGbitDetails() {
  const rows=gbitSelected(),valid=rows.new_id&&rows.original_id;
  $('review-gbit').disabled=busy||!valid||new Set(Object.values(rows).filter(Boolean).map(r=>r.currency)).size>1;
  $('gbit-details').innerHTML=Object.entries(rows).filter(([,row])=>row).map(([name,row])=>`<h3>${{new_id:'New card charge',original_id:'Original expense',refund_id:'Refund deposit'}[name]}</h3>${duplicateCard(row)}`).join('');
  const chosen=Object.values(rows).filter(Boolean);
  const mismatch=chosen.length>1&&chosen.some(row=>row.currency!==chosen[0].currency||units(row.total)!==units(chosen[0].total));
  $('gbit-balance').textContent=mismatch?'Amounts differ. You can still review, provided the currency matches.':valid?'Amounts match. Review the transactions before linking.':'Choose a new charge and the original expense.';
  if(valid&&!rows.refund_id)$('gbit-balance').textContent+=' The GBIT stays incomplete and tagged until its refund is matched.';
}
function renderGbitOriginals() {
  const q=$('gbit-search').value.toLowerCase();
  gbitOptions('gbit-original',gbitData.originals.filter(row=>[row.title,row.total,...row.splits.map(s=>s.source+' '+s.destination)].join(' ').toLowerCase().includes(q)),'Select the original expense…');
  renderGbitDetails();
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
  $('gbit-operations').innerHTML=gbitData.operations.map(op=>`<article class="card history-card"><div class="history-heading"><strong>${fireflyLink(op.plan.rows.original_id.group_id,op.plan.rows.original_id.title)}</strong><span class="status">${esc(op.state)}</span></div><p>${activityTimestamp(op.created)}</p><p>${fireflyLink(op.plan.rows.new_id.group_id,'New charge #'+op.plan.rows.new_id.group_id)}${op.plan.rows.refund_id?' · '+fireflyLink(op.plan.rows.refund_id.group_id,'Refund #'+op.plan.rows.refund_id.group_id):' · Awaiting refund'}</p>${op.result?.error?`<p>${esc(op.result.error)}</p>`:''}${!['complete','awaiting_refund'].includes(op.state)?`<button class="secondary" data-resume-gbit="${esc(op.plan.id)}">Inspect & resume</button>`:''}</article>`).join('')||'<div class="card empty">Saved GBIT matches will appear here.</div>';
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
    }catch(error){failures.push(`Journal #${id}: ${error.message}`);}
  }
  autoLoadedTools.delete('gbit');autoLoadedTools.delete('duplicates');autoLoadedTools.delete('reimbursements');
  renderValidation();notice(`${count} transaction${count===1?'':'s'} marked as GBIT (cash applied, todo removed).${failures.length?'\n'+failures.join('\n')+'\nSome cash changes may have completed. Reload Transaction review or inspect Activity.':''}`,!failures.length);
}
function showGbitReview(plan) {
  gbitPlan=plan;
  $('gbit-review-status').textContent='';
  $('gbit-review-content').innerHTML=Object.entries(plan.rows).map(([name,row])=>`<h3>${{original_id:'Original expense',new_id:'New charge',refund_id:'Refund deposit'}[name]}</h3>${duplicateCard(row)}`).join('')+`<p>Original expense → new charge: <strong>${esc(plan.link_names?.GBIT||'GBIT')}</strong>.</p>${plan.rows.refund_id?`<p>Original expense → refund deposit: <strong>${esc(plan.link_names?.['GBIT Refund']||'GBIT Refund')}</strong>.</p><p>GBIT tags are removed only after both link types are verified.</p>`:'<p>Only the GBIT charge link will be created. Tags remain until the refund is matched.</p>'}<p>${plan.links.length} journal links will be verified. Existing matching links are reused.</p>`;
  $('gbit-dialog').showModal();
}
$('load-gbit').addEventListener('click',()=>perform(loadGbit));
$('gbit-new').addEventListener('change',renderGbitDetails);
$('gbit-original').addEventListener('change',renderGbitDetails);
$('gbit-refund').addEventListener('change',renderGbitDetails);
$('gbit-search').addEventListener('input',renderGbitOriginals);
$('gbit-selected').addEventListener('click',()=>perform(()=>flagGbit([...validationSelected])));
$('review-gbit').addEventListener('click',()=>perform(async()=>showGbitReview(await api('/api/gbit/review',{original_id:$('gbit-original').value,new_id:$('gbit-new').value,refund_id:$('gbit-refund').value}))));
$('gbit-operations').addEventListener('click',event=>{
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
  await loadGbit();
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
  return changes;
}
function categorizeControls() {
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
  $('categorize-status').textContent='Loading current transactions and choices from Firefly…';
  $('categorize-targets').innerHTML='';
  for(const id of Object.values(categorizeFields))categorizeOptions(id,[]);
  $('categorize-dialog').showModal();
  try {
    categorizeSession=await api('/api/validation/categorize-options',{journal_ids:categorizeIds});
    for(const [field,id] of [['source_id','categorize-source'],['destination_id','categorize-destination']]) {
      const allowed=categorizeSession.accounts.filter(account=>categorizeSession.transactions.every(row=>row.allowed_accounts[field].includes(account.id)));
      categorizeOptions(id,allowed);
    }
    categorizeOptions('categorize-category',categorizeSession.categories,true);
    categorizeOptions('categorize-budget',categorizeSession.budgets,true);
    categorizeOptions('categorize-bill',categorizeSession.bills,true);
    $('categorize-target-count').textContent=`${categorizeIds.length} selected transaction journal${categorizeIds.length===1?'':'s'}`;
    $('categorize-targets').innerHTML=categorizeSession.transactions.map(row=>`<p>${fireflyLink(row.group_id,row.description)} · Journal #${esc(row.journal_id)}<br>${esc(row.source_name)} → ${esc(row.destination_name)} · ${esc(fmt(row.amount,row.currency_code))}<br>Category: ${esc(row.category_name||'None')} · Budget: ${esc(row.budget_name||'None')} · Subscription: ${esc(row.bill_name||'None')}</p>`).join('');
    $('categorize-help').textContent='Account choices are valid for every selected transaction type. For mixed types, categorize accounts separately if no common choice exists. Budget and subscription changes affect withdrawals only.';
    $('categorize-status').textContent='Choose fields to change, then apply.';
    categorizeControls();
  }catch(error){$('categorize-status').textContent=error.message;throw error;}
}
$('categorize-selected').addEventListener('click',()=>perform(()=>openCategorize([...validationSelected])));
for(const id of Object.values(categorizeFields))$(id).addEventListener('change',categorizeControls);
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
    $('categorize-status').textContent=`${completed} updated. Failed transactions remain selected in this dialog.\n`+failures.map(item=>`Journal #${item.jid}: ${item.error}`).join('\n')+reloadError;
    categorizeControls();
  }else {
    $('categorize-dialog').close();categorizeSession=undefined;
    notice(`${completed} transaction journal${completed===1?'':'s'} categorized. Tags kept.${reloadError}`,!reloadError);
  }
}));
