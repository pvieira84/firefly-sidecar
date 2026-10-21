'use strict';
const $ = id => document.getElementById(id);
let config, data = {deposits: [], expenses: []}, selected = new Set(), plan, busy = false;
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value, currency) => { try { return new Intl.NumberFormat(undefined, {style:'currency',currency}).format(value); } catch { return `${value} ${currency}`; } };
const date = s => String(s || '').slice(0,10);
// Exact decimal arithmetic (Firefly supports up to 12 decimal places).
function units(value) {
  const match = /^(\d+)(?:\.(\d{1,12}))?$/.exec(String(value));
  if (!match) throw new Error('Unsupported amount format. Refresh or inspect this transaction in Firefly.');
  return BigInt(match[1]) * 1000000000000n + BigInt((match[2] || '').padEnd(12,'0'));
}
function decimal(value) { const s = value.toString().padStart(13,'0'); return s.slice(0,-12)+'.'+s.slice(-12); }
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
  for(const id of ['refresh','filter-dates','review','apply','test-connection','cancel-review']) $(id).disabled=value;
  $('deposit').disabled=value;
  renderExpenses();
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
    $('balance-help').textContent='Selected splits must match the full deposit, in the same currency.';
    $('deposit-detail').textContent='Choose an incoming payment to start matching.';
  } else {
    const total=totals.get(d.currency_code)||0n, remaining=units(d.amount)-total;
    valid=items.length>0 && items.length<=100 && totals.size===1 && remaining===0n;
    $('deposit-detail').textContent=`${date(d.date)} · ${d.source_name} → ${d.destination_name} · Journal #${d.journal_id}`;
    $('balance-label').textContent=valid?'Exact match — ready to review':remaining<0n?'Selection exceeds the deposit':`${fmt(decimal(remaining),d.currency_code)} left to match`;
    $('balance-help').textContent=valid?'Each selected split will be linked to this deposit.': 'Choose whole reimbursement splits totaling '+fmt(d.amount,d.currency_code)+'.';
  }
  $('review').disabled=busy || !valid;
}
function renderExpenses() {
  const d=currentDeposit(), q=$('search').value.toLowerCase();
  const rows=data.expenses.filter(x=>[x.group_title,x.description,x.destination_name,x.source_name,x.amount,x.journal_id].join(' ').toLowerCase().includes(q));
  $('expenses').innerHTML=rows.map(x=>{
    const disabled=!!d && x.currency_code!==d.currency_code;
    return `<tr class="${selected.has(x.journal_id)?'selected ':''}${disabled?'unavailable':''}"><td><input type="checkbox" aria-label="Select ${esc(x.group_title||x.destination_name)} reimbursement ${esc(x.journal_id)}" data-journal="${esc(x.journal_id)}" ${selected.has(x.journal_id)?'checked':''} ${disabled||busy?'disabled':''}></td><td><strong>${esc(x.group_title||x.destination_name||x.description)}</strong><small>${esc(x.description)} · ${esc(x.destination_name)} · Split #${esc(x.journal_id)}</small></td><td>${esc(date(x.date))}</td><td>${esc(x.source_name)}</td><td class="right"><strong>${esc(fmt(x.amount,x.currency_code))}</strong>${disabled?'<small>Different currency</small>':''}</td></tr>`;
  }).join('')||'<tr><td colspan="5" class="empty">'+(data.expenses.length?'No expenses match your search.':'No pending reimbursement splits. You’re all caught up.')+'</td></tr>';
  $('visible-count').textContent=`${rows.length} of ${data.expenses.length} pending splits`;
  renderBalance();
}
async function load() {
  const query=new URLSearchParams({start:$('start').value,end:$('end').value});
  const old=$('deposit').value;
  data=await api('/api/reimbursements?'+query);
  selected=new Set([...selected].filter(id=>data.expenses.some(x=>x.journal_id===id)));
  $('deposit').innerHTML='<option value="">Select a deposit…</option>'+data.deposits.map(x=>`<option value="${esc(x.journal_id)}">${esc(date(x.date))} · ${esc(x.description)} · ${esc(fmt(x.amount,x.currency_code))} · #${esc(x.journal_id)}</option>`).join('');
  if(data.deposits.some(x=>x.journal_id===old)) $('deposit').value=old;
  renderStats(); renderExpenses();
}
function renderPlan(p) {
  plan=p;
  const d=p.deposit;
  $('review-content').innerHTML=`<div class="review-deposit"><strong>${esc(d.description)}</strong><p>${esc(date(d.date))} · ${esc(d.source_name)} · Deposit #${esc(d.transaction_journal_id)}</p><strong>${esc(fmt(d.amount,p.currency))}</strong></div>`+p.expenses.map(x=>`<div class="review-line"><div>${esc(x.group_title||x.destination_name)}<br><small>Reimbursement split #${esc(x.journal_id)}</small></div><strong>${esc(fmt(x.amount,x.currency_code))}</strong></div>`).join('')+`<div class="review-line review-total"><span>Total to settle</span><span>${esc(fmt(p.total,p.currency))}</span></div><p class="review-note">Expense split <b>${esc(p.link_type.inward)}</b> deposit.<br>Each verified link is followed by removal of the <b>${esc(p.tag)}</b> tag from that expense split. Other tags are preserved.</p>`;
  $('review-dialog').showModal();
}
async function applyPlan(id) {
  const r=await api('/api/reimbursements/apply',{plan_id:id});
  if($('review-dialog').open) $('review-dialog').close();
  if(r.complete) { notice(`Reimbursement complete. ${r.items.length} split${r.items.length===1?'':'s'} linked and pending tags removed.`,true); selected.clear(); }
  else { notice('Operation paused. Some changes may have completed. Open Activity to inspect the result and retry.\n'+r.items.filter(x=>x.error).map(x=>`Split #${x.journal_id}: ${x.error}`).join('\n')); }
  await load(); await loadHistory();
}
async function loadHistory() {
  const rows=await api('/api/history');
  $('history-list').innerHTML=rows.map(x=>`<article class="card history-card"><div class="history-heading"><strong>${esc(x.plan.deposit.description)} · ${esc(fmt(x.plan.total,x.plan.currency))}</strong><span class="status">${esc(x.state)}</span></div><p>${esc(x.created.slice(0,19).replace('T',' '))} UTC · ${x.plan.expenses.length} splits · Deposit #${esc(x.plan.deposit.transaction_journal_id)}</p><ul>${(x.result?.items||[]).map(i=>`<li>Split #${esc(i.journal_id)}: ${esc(i.status)}${i.error?' — '+esc(i.error):''}</li>`).join('')}</ul>${x.state!=='complete'?`<button class="secondary" data-resume="${esc(x.id)}">${x.state==='review'?'Open review':'Inspect & resume'}</button>`:''}</article>`).join('')||'<div class="card empty">Your reimbursement activity will appear here.</div>';
  $('history-list').querySelectorAll('[data-resume]').forEach(button=>button.addEventListener('click',()=>perform(async()=>renderPlan(rows.find(x=>x.id===button.dataset.resume).plan))));
}
async function view(name) {
  document.querySelectorAll('.view').forEach(x=>x.hidden=x.id!==name);
  document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.view===name));
  $('breadcrumb').textContent={reimbursements:'Reimbursements',history:'Activity',connection:'Connection'}[name];
  if(name==='history') await loadHistory();
}
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>perform(()=>view(button.dataset.view))));
$('refresh').addEventListener('click',()=>perform(load));
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
  try {
    config=await api('/api/bootstrap');
    $('connection-url').textContent=config.firefly_url||'No server configured';
    $('connection-state').textContent=config.configured?'Credentials configured on server. Test the connection below.':'Configuration required.';
    $('matching-rules').textContent=`Pending tag: ${config.tag}. Description defaults to “Reimbursement”; category must be empty. These rules can be changed using REIMBURSE_TAG and REIMBURSE_DESCRIPTION.`;
    if(!config.configured){await view('connection');notice('Add your Firefly III URL and API token to the Docker environment to get started.');return;}
    await perform(load);
  } catch(e) { notice(e.message); }
})();
