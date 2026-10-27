import tempfile
import threading
import unittest
from unittest.mock import patch
from sidecar.client import Problem
from sidecar.store import Store
from sidecar.auditing import AuditedFirefly
from sidecar.tools.validation import Validation
from test_reimbursements import FakeFirefly


class RefundTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(self.tmp.name+'/audit.db')
        self.raw=FakeFirefly()
        for row,amount in zip(self.raw.groups['100']['attributes']['transactions'],('19.70','0.59','19.70')):
            row['amount']=amount
        self.raw.groups['200']['attributes']['transactions'][0].update(amount='39.99',tags=['todo','Keep'],destination_id='1')
        self.tool=Validation(AuditedFirefly(self.raw,self.store),threading.Lock())

    def tearDown(self):self.tmp.cleanup()

    def search(self, **kwargs):
        return self.tool.refund_candidates({'deposit_id':'21',**kwargs})

    def apply(self, result, remove=False):
        return self.tool.mark_refund({'token':result['token'],'group_id':'100','remove_todo':remove})

    def test_split_total_match_direction_audit_and_keep_todo(self):
        result=self.search()
        self.assertEqual(result['candidates'][0]['total'],'39.99')
        self.assertEqual(self.raw.writes,[])
        self.assertTrue(self.apply(result)['complete'])
        self.assertEqual(len(self.raw.linkdata),3)
        for link in self.raw.linkdata:
            self.assertEqual(link['link_type_id'],'5')
            self.assertEqual(link['inward_id'],'21')
            self.assertIn(link['outward_id'],['11','12','13'])
        self.assertEqual(self.raw.journal('21')[1]['tags'],['todo','Keep'])
        self.assertEqual(sum(e['action']=='Create Refund link' for e in self.store.events()['events']),3)
        self.apply(result)
        self.assertEqual(len(self.raw.linkdata),3)

    def test_optional_todo_removal_and_partial_failure_retry(self):
        result=self.search()
        self.raw.fail_tag=True
        with self.assertRaises(Problem):self.apply(result,True)
        self.assertEqual(len(self.raw.linkdata),3)
        self.assertIn('todo',self.raw.journal('21')[1]['tags'])
        self.apply(result,True)
        self.assertEqual(len(self.raw.linkdata),3)
        self.assertEqual(self.raw.journal('21')[1]['tags'],['Keep'])

    def test_lost_link_response_retry_does_not_duplicate(self):
        result=self.search();self.raw.lose_link_response=True
        with self.assertRaises(Problem):self.apply(result)
        self.assertEqual(len(self.raw.linkdata),1)
        self.apply(result)
        self.assertEqual(len(self.raw.linkdata),3)

    def test_date_currency_tolerance_filters_and_defaults(self):
        with patch.dict('os.environ',{'REFUND_LOOKBACK_DAYS':'30','REFUND_AMOUNT_TOLERANCE':'0.01'}):
            result=self.search()
        self.assertEqual(result['start'],'2026-09-20')
        self.assertEqual(result['tolerance'],'0.01')
        self.raw.groups['200']['attributes']['transactions'][0]['amount']='40.99'
        self.assertEqual(len(self.search(tolerance='1')['candidates']),1)
        self.assertEqual(len(self.search(tolerance='0.99')['candidates']),0)
        self.assertEqual(len(self.search(start='2026-10-21',end='2026-10-22')['candidates']),0)
        self.raw.groups['200']['attributes']['transactions'][0]['currency_code']='USD'
        self.assertEqual(self.search()['candidates'],[])

    def test_deposits_only_stale_and_unselected_withdrawal_block_writes(self):
        with self.assertRaises(Problem):self.tool.refund_candidates({'deposit_id':'12'})
        result=self.search()
        with self.assertRaises(Problem):self.tool.mark_refund({'token':result['token'],'group_id':'999'})
        self.raw.groups['100']['attributes']['transactions'][0]['amount']='20.00'
        with self.assertRaises(Problem):self.apply(result)
        self.assertEqual(self.raw.writes,[])

    def test_expired_search_and_bad_filters(self):
        result=self.search();self.tool.refund_previews[result['token']]['created']-=601
        with self.assertRaises(Problem):self.apply(result)
        for tolerance in ('-1','NaN','Infinity','bad'):
            with self.assertRaises(Problem):self.search(tolerance=tolerance)
        self.assertEqual(self.raw.writes,[])

    def test_conflicting_deposit_refund_link_is_blocked(self):
        result=self.search()
        self.raw.linkdata=[{'link_type_id':'5','inward_id':'999','outward_id':'21'}]
        with self.assertRaises(Problem):self.apply(result)
        self.assertEqual(self.raw.writes,[])

    def test_cross_account_default_and_same_account_opt_in(self):
        self.raw.groups['200']['attributes']['transactions'][0]['destination_id']='99'
        filtered=self.search(same_account=True)
        self.assertEqual(filtered['candidates'],[])
        self.assertEqual(filtered['excluded_same_account'],1)
        result=self.search()
        self.assertEqual(len(result['candidates']),1)
        self.assertFalse(result['same_account'])
        self.apply(result)
        self.assertEqual(self.raw.journal('21')[1]['destination_id'],'99')

    def test_both_sides_marked_cash_without_changing_amounts_or_tags(self):
        for row in self.raw.groups['100']['attributes']['transactions']:
            row.update(category_id='5',category_name='Dining',budget_id='10',budget_name='Food',bill_id='4',bill_name='Bill')
        deposit=self.raw.groups['200']['attributes']['transactions'][0]
        deposit.update(category_id='6',category_name='Income',budget_id='11',budget_name='Other',bill_id='5',bill_name='Other bill')
        result=self.search();self.apply(result)
        for jid in ('11','12','13'):
            row=self.raw.journal(jid)[1]
            self.assertEqual(row['source_id'],'1')
            self.assertEqual(row['destination_id'],'7')
            self.assertIsNone(row['category_id']);self.assertIsNone(row['budget_id']);self.assertIsNone(row['bill_id'])
        deposit=self.raw.journal('21')[1]
        self.assertEqual(deposit['source_id'],'7')
        self.assertEqual(deposit['destination_id'],'1')
        self.assertEqual(deposit['amount'],'39.99')
        self.assertEqual(deposit['tags'],['todo','Keep'])
        self.assertEqual(sum(e['action']=='Mark as cash' for e in self.store.events()['events']),4)
        writes=len(self.raw.writes)
        self.apply(result)
        self.assertEqual(len(self.raw.writes),writes)

    def test_reversed_sidecar_links_are_repaired_in_place(self):
        result=self.search()
        self.raw.linkdata=[{'link_type_id':'5','inward_id':jid,'outward_id':'21','notes':'Firefly Sidecar refund match'} for jid in ('11','12','13')]
        self.apply(result)
        self.assertEqual(len(self.raw.linkdata),3)
        self.assertTrue(all(link['inward_id']=='21' for link in self.raw.linkdata))
        self.assertEqual({link['outward_id'] for link in self.raw.linkdata},{'11','12','13'})
        events=self.store.events()['events']
        self.assertEqual(sum(e['action']=='Correct Refund link direction' for e in events),3)
        self.assertFalse(any(method=='POST' for method,path,body in self.raw.writes))

    def test_reversed_unowned_links_are_not_changed(self):
        result=self.search()
        self.raw.linkdata=[{'link_type_id':'5','inward_id':'11','outward_id':'21','notes':'Manual link'}]
        with self.assertRaises(Problem):self.apply(result)
        self.assertEqual(self.raw.writes,[])

    def test_selected_splits_only_are_linked_and_marked_cash(self):
        import copy
        result=self.search()
        before=copy.deepcopy(self.raw.groups['100']['attributes']['transactions'])
        body={'token':result['token'],'group_id':'100','journal_ids':['11','12']}
        applied=self.tool.mark_refund(body)
        self.assertEqual(applied['links'],2)
        self.assertEqual({link['outward_id'] for link in self.raw.linkdata},{'11','12'})
        self.assertEqual(self.raw.journal('13')[1],before[2])
        self.assertEqual(self.raw.journal('11')[1]['destination_id'],'7')
        count=len(self.raw.writes)
        self.tool.mark_refund(body)
        self.assertEqual(len(self.raw.writes),count)

    def test_split_expense_remains_searchable_for_individual_refund(self):
        self.raw.groups['200']['attributes']['transactions'][0]['amount']='19.70'
        result=self.search(tolerance='0')
        self.assertEqual([row['group_id'] for row in result['candidates']],['100'])
        applied=self.tool.mark_refund({'token':result['token'],'group_id':'100','journal_ids':['11']})
        self.assertEqual(applied['links'],1)
        self.assertEqual(self.raw.linkdata[0]['inward_id'],'21')
        self.assertEqual(self.raw.linkdata[0]['outward_id'],'11')

    def test_invalid_split_selection_does_not_write(self):
        result=self.search()
        for selection in ([],None,'11',['999'],['21'],['11','11']):
            with self.assertRaises(Problem):
                self.tool.mark_refund({'token':result['token'],'group_id':'100','journal_ids':selection})
        self.assertEqual(self.raw.writes,[])


    def test_gift_card_refund_finds_purchase_plus_fee_and_links_selected_split(self):
        purchase,fee=self.raw.groups['100']['attributes']['transactions'][:2]
        purchase.update(amount='30.19',date='2026-10-08T00:00:00+01:00',source_id='435',description='Purchase')
        fee.update(amount='0.45',date='2026-10-08T00:00:00+01:00',source_id='435',description='Fee')
        self.raw.groups['100']['attributes']['transactions']=[purchase,fee]
        deposit=self.raw.groups['200']['attributes']['transactions'][0]
        deposit.update(amount='30.19',date='2026-10-27T13:15:00+00:00',destination_id='220',source_id='7')
        result=self.search(start='2026-10-08',end='2026-10-08',tolerance='1')
        self.assertEqual([row['group_id'] for row in result['candidates']],['100'])
        self.assertEqual(result['candidates'][0]['total'],'30.64')
        self.assertEqual(result['candidates'][0]['difference'],'0.45')
        self.assertFalse(result['same_account'])
        self.assertEqual(self.search(start='2026-10-08',end='2026-10-08',tolerance='1',same_account=True)['excluded_same_account'],1)
        before_fee=dict(fee)
        self.tool.mark_refund({'token':result['token'],'group_id':'100','journal_ids':['11']})
        self.assertEqual([(link['inward_id'],link['outward_id']) for link in self.raw.linkdata],[('21','11')])
        self.assertEqual(self.raw.journal('12')[1],before_fee)
        self.assertEqual(self.raw.journal('21')[1]['destination_id'],'220')
        self.assertEqual(self.raw.journal('11')[1]['source_id'],'435')
