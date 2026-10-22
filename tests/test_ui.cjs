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
  Intl, URL, URLSearchParams
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

vm.runInContext(`busy=false;validationLoaded=true;validationRows=[{journal_id:'11',description:'<Dinner>',tags:['todo','Personal'],category_name:'Dining',amount:'30.00',currency_code:'EUR'}];renderValidation()`, context);
assert(get('validation-rows').innerHTML.includes('&lt;Dinner&gt;'));
assert(get('validation-rows').innerHTML.includes('Personal'));
assert(get('validation-rows').innerHTML.includes('data-validate="11"'));
vm.runInContext('setBusy(true)', context);
assert(get('validation-rows').innerHTML.includes('disabled'));
vm.runInContext('setBusy(false)', context);
assert(!get('validation-rows').innerHTML.includes('disabled'));
get('validation-search').value='absent';
vm.runInContext('renderValidation()',context);
assert(!get('validation-rows').innerHTML.includes('data-validate="11"'));
console.log('Validation queue rendering, escaping, filtering and busy-state checks passed.');

vm.runInContext("config.firefly_url='https://firefly.example/base';",context);
const duplicateMarkup=vm.runInContext(`duplicateCard({group_id:'10',title:'<Dinner>',date:'2026-10-22',type:'withdrawal',total:'39.99',currency:'EUR',tags:['<todo>'],splits:[{journal_id:'11',description:'<split>',amount:'39.99',source:'Bank',destination:'Shop'}]})`,context);
assert(duplicateMarkup.includes('https://firefly.example/base/transactions/show/10'));
assert(duplicateMarkup.includes('&lt;Dinner&gt;'));
assert(duplicateMarkup.includes('&lt;todo&gt;'));
vm.runInContext("config.firefly_url='javascript:alert(1)';",context);
assert.equal(vm.runInContext("fireflyLink('10','Open')",context),'Open');
console.log('Duplicate card details, escaping, and safe Firefly link checks passed.');

assert(vm.runInContext("reviewDuplicateStatus({status:'checked',match_count:0,days:3})",context).includes('No candidates'));
assert(vm.runInContext("reviewDuplicateStatus({status:'unavailable',reason:'<error>'})",context).includes('&lt;error&gt;'));
assert(!vm.runInContext("reviewDuplicateStatus({status:'unavailable',reason:'error'})",context).includes('No candidates'));
assert(vm.runInContext("reviewDuplicateStatus({status:'manual',reason:'Mixed currencies'})",context).includes('Manual review needed'));
console.log('Review duplicate-check status checks passed.');
