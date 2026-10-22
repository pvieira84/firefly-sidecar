import copy
import tempfile
import threading
import unittest
from sidecar.auditing import AuditedFirefly
from sidecar.client import Problem
from sidecar.store import Store
from sidecar.tools.validation import Validation
from sidecar.tools.gbit import GBIT
from test_reimbursements import FakeFirefly, split


class GBITFirefly(FakeFirefly):
    def __init__(self):
        super().__init__()
        self.groups['300']={'id':'300','attributes':{'group_title':'','transactions':[split('31','50.00')]}}
        self.groups['300']['attributes']['transactions'][0].update(tags=['todo','Keep'],category_id='8',category_name='Temporary',budget_id='9',budget_name='Budget',bill_id='10',bill_name='Bill',source_id='3')
        self.groups['200']['attributes']['transactions'][0].update(amount='50.00',tags=['todo','Keep'])

    def all(self,path,**params):
        if path=='link-types':
            return super().all(path,**params)+[{'id':'6','attributes':{'name':'GBIT'}},{'id':'7','attributes':{'name':'GBIT Refund'}}]
        if path.startswith('tags/'):
            return [copy.deepcopy(g) for g in self.groups.values() if any('#GBIT' in (s.get('tags') or []) for s in g['attributes']['transactions'])]
        if path=='transactions':
            return [copy.deepcopy(g) for g in self.groups.values() if g['attributes']['transactions'][0]['type']==params.get('type','withdrawal')]
        return super().all(path,**params)


class GBITTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name+'/gbit.db')
        self.raw=GBITFirefly();self.client=AuditedFirefly(self.raw,self.store);self.lock=threading.RLock()
        self.validation=Validation(self.client,self.lock);self.tool=GBIT(self.client,self.store,self.validation,self.lock)

    def tearDown(self):self.tmp.cleanup()

    def flag(self):
        self.tool.flag({'journal_id':'31'});self.tool.flag({'journal_id':'21'})

    def prepare(self,refund=True):
        body={'original_id':'100','new_id':'300'}
        if refund:body['refund_id']='200'
        return self.tool.prepare(body)

    def test_flag_withdrawal_and_deposit_cash_tag_and_todo(self):
        self.flag()
        charge=self.raw.journal('31')[1];refund=self.raw.journal('21')[1]
        self.assertEqual(charge['destination_id'],'7');self.assertEqual(refund['source_id'],'7')
        for row in (charge,refund):
            self.assertEqual(row['tags'],['Keep','#GBIT'])
            self.assertIsNone(row.get('category_id'));self.assertIsNone(row.get('budget_id'));self.assertIsNone(row.get('bill_id'))
        data=self.tool.listing('2026-10-01','2026-10-22')
        self.assertEqual([r['group_id'] for r in data['new_expenses']],['300'])
        self.assertEqual([r['group_id'] for r in data['refunds']],['200'])
        self.assertEqual([r['group_id'] for r in data['originals']],['100'])

    def test_complete_match_preserves_original_and_links_every_journal(self):
        self.flag();original=copy.deepcopy(self.raw.groups['100'])
        plan=self.prepare();before=len(self.raw.writes)
        self.assertEqual(len(self.raw.writes),before)
        result=self.tool.apply({'plan_id':plan['id']})
        self.assertTrue(result['complete']);self.assertEqual(result['links'],6)
        self.assertEqual(self.raw.groups['100'],original)
        expected={('6',jid,'31') for jid in ('11','12','13')}|{('7',jid,'21') for jid in ('11','12','13')}
        self.assertEqual({(r['link_type_id'],r['inward_id'],r['outward_id']) for r in self.raw.linkdata},expected)
        self.assertEqual(self.raw.journal('31')[1]['tags'],['Keep'])
        self.assertEqual(self.raw.journal('21')[1]['tags'],['Keep'])
        self.assertEqual(self.store.operation(plan['id'],'gbit')[1],'complete')
        count=len(self.raw.writes);self.tool.apply({'plan_id':plan['id']});self.assertEqual(len(self.raw.writes),count)

    def test_charge_first_keeps_tags_then_completes_when_refund_arrives(self):
        self.flag();partial=self.prepare(False)
        result=self.tool.apply({'plan_id':partial['id']})
        self.assertTrue(result['awaiting_refund']);self.assertEqual(len(self.raw.linkdata),3)
        self.assertIn('#GBIT',self.raw.journal('31')[1]['tags'])
        full=self.prepare();self.assertTrue(self.tool.apply({'plan_id':full['id']})['complete'])
        self.assertEqual(len(self.raw.linkdata),6)
        self.assertEqual(self.store.operation(partial['id'],'gbit')[1],'complete')

    def test_interrupted_link_and_restart_reuse_links(self):
        self.flag();plan=self.prepare();self.raw.lose_link_response=True
        result=self.tool.apply({'plan_id':plan['id']})
        self.assertFalse(result['complete']);self.assertIn('#GBIT',self.raw.journal('31')[1]['tags'])
        restarted=GBIT(self.client,Store(self.store.filename),self.validation,self.lock)
        self.assertTrue(restarted.apply({'plan_id':plan['id']})['complete'])
        self.assertEqual(len(self.raw.linkdata),6)

    def test_tag_cleanup_failure_can_resume_after_verified_links(self):
        self.flag();plan=self.prepare();self.raw.fail_tag=True
        result=self.tool.apply({'plan_id':plan['id']})
        self.assertFalse(result['complete']);self.assertEqual(len(self.raw.linkdata),6)
        self.assertIn('#GBIT',self.raw.journal('31')[1]['tags'])
        self.assertTrue(self.tool.apply({'plan_id':plan['id']})['complete'])
        self.assertEqual(len(self.raw.linkdata),6)

    def test_stale_or_conflicting_match_blocks_writes(self):
        self.flag();plan=self.prepare();self.raw.groups['100']['attributes']['transactions'][0]['amount']='31.00'
        count=len(self.raw.writes)
        with self.assertRaises(Problem):self.tool.apply({'plan_id':plan['id']})
        self.assertEqual(len(self.raw.writes),count)

    def test_missing_types_and_mixed_currencies_block_review(self):
        self.flag();self.raw.groups['200']['attributes']['transactions'][0]['currency_code']='USD'
        with self.assertRaises(Problem):self.prepare()

    def test_flag_entire_split_parent_and_transfer_rejected(self):
        group=self.raw.groups['300'];extra=copy.deepcopy(group['attributes']['transactions'][0]);extra.update(transaction_journal_id='32',amount='5.00')
        group['attributes']['transactions'].append(extra);group['attributes']['group_title']='GBIT splits'
        self.tool.flag({'journal_id':'31'})
        for jid in ('31','32'):
            row=self.raw.journal(jid)[1];self.assertEqual(row['destination_id'],'7');self.assertEqual(row['tags'],['Keep','#GBIT'])
        self.raw.groups['200']['attributes']['transactions'][0]['type']='transfer'
        count=len(self.raw.writes)
        with self.assertRaises(Problem):self.tool.flag({'journal_id':'21'})
        self.assertEqual(len(self.raw.writes),count)

    def test_conflicting_original_link_blocks_review(self):
        self.flag()
        self.raw.linkdata=[{'link_type_id':'6','inward_id':'11','outward_id':'999'}]
        count=len(self.raw.writes)
        with self.assertRaises(Problem):self.prepare()
        self.assertEqual(len(self.raw.writes),count)

    def test_new_charge_already_assigned_to_another_original_is_blocked(self):
        self.flag()
        self.raw.linkdata=[{'link_type_id':'6','inward_id':'999','outward_id':'31'}]
        count=len(self.raw.writes)
        with self.assertRaises(Problem):self.prepare()
        self.assertEqual(len(self.raw.writes),count)

    def test_custom_link_names_and_saved_plan_bindings(self):
        from unittest.mock import patch
        original_all=self.raw.all
        def custom_all(path,**params):
            result=original_all(path,**params)
            if path=='link-types':
                for item in result:
                    if item['attributes']['name']=='GBIT':item['attributes']['name']='Curve move'
                    if item['attributes']['name']=='GBIT Refund':item['attributes']['name']='Curve credit'
            return result
        self.raw.all=custom_all
        with patch.dict('os.environ',{'GBIT_LINK_TYPE':'Curve move','GBIT_REFUND_LINK_TYPE':'Curve credit'}):
            tool=GBIT(self.client,self.store,self.validation,self.lock)
        self.flag()
        plan=tool.prepare({'original_id':'100','new_id':'300','refund_id':'200'})
        self.assertEqual(plan['link_names'],{'GBIT':'Curve move','GBIT Refund':'Curve credit'})
        self.assertEqual(plan['link_types'],{'GBIT':'6','GBIT Refund':'7'})
        # Reloading with default config must not change the saved operation's bindings.
        self.assertTrue(self.tool.apply({'plan_id':plan['id']})['complete'])

    def test_empty_or_identical_link_names_rejected(self):
        from unittest.mock import patch
        for settings in ({'GBIT_LINK_TYPE':''},{'GBIT_LINK_TYPE':'Same','GBIT_REFUND_LINK_TYPE':'Same'}):
            with patch.dict('os.environ',settings):
                with self.assertRaises(ValueError):GBIT(self.client,self.store,self.validation,self.lock)
