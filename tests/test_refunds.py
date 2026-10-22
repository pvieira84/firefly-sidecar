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
        self.raw.groups['200']['attributes']['transactions'][0].update(amount='39.99',tags=['todo','Keep'])
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
            self.assertEqual(link['outward_id'],'21')
            self.assertIn(link['inward_id'],['11','12','13'])
        self.assertEqual(self.raw.journal('21')[1]['tags'],['todo','Keep'])
        self.assertTrue(all(e['action']=='Create Refund link' for e in self.store.events()['events']))
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
