// Run with node tests/test_ui.cjs. Exercises UI behavior without a browser.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
const get = id => {
  if (!elements.has(id)) elements.set(id, {
    value: '', innerHTML: '', textContent: '', disabled: false,
    addEventListener() {}, showModal() { this.open = true; }
  });
  return elements.get(id);
};
const calls = [];
const context = vm.createContext({
  document: {getElementById: get, querySelectorAll: () => []},
  fetch: path => { calls.push(path); return new Promise(() => {}); },
  Intl, URLSearchParams
});
vm.runInContext(fs.readFileSync('sidecar/static/app.js', 'utf8'), context);
assert.deepEqual(calls, ['/api/bootstrap']);
const localDate=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const today=new Date(), weekAgo=new Date(today);
weekAgo.setDate(weekAgo.getDate()-7);
assert.equal(get('start').value, localDate(weekAgo));
assert.equal(get('end').value, localDate(today));
vm.runInContext(`
config={tag:'Reimburse'}; loaded=true;
data={deposits:[{journal_id:'21',transaction_journal_id:'21',amount:'20.00',currency_code:'EUR'}],
      expenses:[{journal_id:'12',amount:'15.00',currency_code:'EUR',tags:['Trip','Reimburse']}]};
`, context);
get('deposit').value = '21';
for (const [total, expectedWarning] of [['15.00', 'less'], ['25.00', 'more'], ['20.00', '']]) {
  vm.runInContext(`data.expenses[0].amount='${total}';selected=new Set(['12']);renderBalance();`, context);
  assert.equal(get('review').disabled, false);
  if (expectedWarning) assert(get('balance-help').textContent.includes(expectedWarning));
  vm.runInContext(`renderPlan({deposit:data.deposits[0],expenses:data.expenses,total:'${total}',currency:'EUR',tag:'Reimburse',link_type:{inward:'is reimbursed by'}})`, context);
  assert.equal(get('review-content').innerHTML.includes('class="match-warning"'), !!expectedWarning);
  if (expectedWarning) assert(get('review-content').innerHTML.includes(expectedWarning));
}
vm.runInContext('selected.clear();renderBalance()', context);
assert.equal(get('review').disabled, true);
get('deposit').value = '';
vm.runInContext("selected=new Set(['12']);renderBalance()", context);
assert.equal(get('review').disabled, true);
get('deposit').value = '21';
vm.runInContext("data.expenses[0].currency_code='USD';renderBalance()", context);
assert.equal(get('review').disabled, true);
vm.runInContext("data.expenses[0].currency_code='EUR';busy=true;renderBalance()", context);
assert.equal(get('review').disabled, true);
console.log('UI totals, mismatch warnings, and review-button checks passed.');
