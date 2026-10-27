import copy
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from sidecar.tools.amazon import Amazon
from sidecar.auditing import AuditedFirefly
from sidecar.store import Store
from sidecar.client import Problem
from test_reimbursements import FakeFirefly
from test_amazon import order


class PaymentFirefly(FakeFirefly):
    def __init__(self):
        super().__init__();self.lose_creation=False;self.reject_creation=False

    def all(self,path,**params):
        if path in ('categories','budgets','bills'):return [{'id':'7','attributes':{'name':'Assignment','active':True}}]
        if path=='accounts':return [{'id':'8','attributes':{'name':'Amazon','type':'expense','active':True}}, {'id':'9','attributes':{'name':'Amazon Gift Card','type':'asset','active':True,'currency_code':'EUR'}}]
        if path=='link-types':return [{'id':'8','attributes':{'name':'Related'}}]
        if path=='transactions':return copy.deepcopy(list(self.groups.values()))
        return super().all(path,**params)

    def request(self,method,path,body=None,**params):
        if method=='POST' and path=='transactions':
            self.writes.append((method,path,copy.deepcopy(body)))
            if self.reject_creation:raise Problem('Unavailable',502)
            split=copy.deepcopy(body['transactions'][0]);split.update(transaction_journal_id='31',source_name='Amazon Gift Card')
            created={'id':'300','attributes':{'group_title':None,'transactions':[split]}}
            self.groups['300']=created
            if self.lose_creation:self.lose_creation=False;raise Problem('Lost create response',502)
            return {'data':copy.deepcopy(created)}
        return super().request(method,path,body,**params)


class AmazonPaymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name+'/db')
        self.fake=PaymentFirefly();self.tool=Amazon(AuditedFirefly(self.fake,self.store),self.store,threading.RLock())
        self.tool.ingest({'orders':[order(giftCardAmount='30.19')]});self.key=self.tool.orders()[0]['key']
        self.env=patch.dict(os.environ,{'AMAZON_GIFT_CARD_ACCOUNT_ID':'9','AMAZON_GIFT_CARD_TAG':'Gift Paid'});self.env.start()

    def tearDown(self):self.env.stop();self.tmp.cleanup()

    def gift(self,amount='12.34'):
        return self.tool.gift_review({'order_key':self.key,'journal_id':'11','amount':amount})

    def test_transfers_into_gift_account_can_be_matched_and_preserve_financial_fields(self):
        original=copy.deepcopy(self.fake.groups['100']['attributes']['transactions'][0])
        transfer=dict(original,transaction_journal_id='41',type='transfer',destination_id='9',destination_name='Gift card')
        excluded=dict(transfer,transaction_journal_id='42',destination_id='10')
        self.fake.groups['400']={'id':'400','attributes':{'group_title':'Gift funding','transactions':[transfer,excluded]}}
        options=self.tool.manual_options({'order_key':self.key,'start':'2026-10-01','end':'2026-10-31'})
        self.assertIn('41',[r['journal_id'] for r in options['journals']])
        self.assertNotIn('42',[r['journal_id'] for r in options['journals']])
        with self.assertRaises(Problem): self.tool.manual_review({'order_key':self.key,'journal_ids':['42']})
        plan=self.tool.manual_review({'order_key':self.key,'journal_ids':['41']})
        self.tool.manual_apply({'plan_id':plan['id']})
        after=self.fake.groups['400']['attributes']['transactions']
        for field in ('type','amount','source_id','destination_id'):
            self.assertEqual(after[0][field],transfer[field])
        self.assertEqual(after[1],excluded)
        listing=self.tool.listing('2026-10-01','2026-10-31')
        self.assertEqual(listing['orders'][0]['manual_journals'][0]['journal_id'],'41')

    def test_gift_default_and_zero_gift_rejection(self):
        self.assertEqual(self.tool.gift_options({'order_key':self.key})['amount'],'30.19')
        self.assertEqual(self.tool.gift_review({'order_key':self.key,'journal_id':'11'})['transaction']['amount'],'30.19')
        self.tool.ingest({'orders':[order(giftCardAmount=0)]})
        with self.assertRaises(Problem): self.tool.gift_options({'order_key':self.key})
        with self.assertRaises(Problem): self.gift()

    def test_round_gift_amount(self):
        self.assertEqual(self.gift('1.005')['transaction']['amount'], '1.01')

    def standalone(self):
        return self.tool.gift_review({'order_key':self.key, 'amount':'15.555', 'transaction':{
            'description':'Amazon gift purchase', 'date':'2026-10-20', 'destination_id':'8',
            'category_id':'7', 'budget_id':'7', 'bill_id':'7', 'source_id':'1', 'tags':['wrong'], 'type':'deposit'}})

    def test_standalone_withdrawal_assignments_and_retry_without_link(self):
        plan = self.standalone()
        self.assertIsNone(plan['journal_id'])
        self.assertEqual(plan['transaction']['type'],'withdrawal')
        self.assertEqual(plan['transaction']['source_id'],'9')
        self.assertEqual(plan['transaction']['tags'],['Gift Paid'])
        self.assertEqual(plan['transaction']['amount'],'15.56')
        self.assertEqual(plan['transaction']['category_id'],'7')
        self.assertEqual(plan['transaction']['budget_id'],'7')
        self.assertEqual(plan['transaction']['bill_id'],'7')
        self.fake.lose_creation=True
        with self.assertRaises(Problem): self.tool.gift_apply({'plan_id':plan['id']})
        result=self.tool.gift_apply({'plan_id':plan['id']})
        self.assertTrue(result['complete'])
        self.tool.gift_apply({'plan_id':plan['id']})
        self.assertEqual(len(self.fake.writes),1)
        self.assertEqual(len(self.fake.groups['300']['attributes']['transactions']),1)
        self.assertEqual(self.fake.linkdata,[])

    def test_standalone_rejects_invalid_destination_and_missing_description(self):
        for details in ({'description':'Purchase','date':'2026-10-20','destination_id':'9'}, {'description':'','date':'2026-10-20','destination_id':'8'}):
            with self.assertRaises(Problem): self.tool.gift_review({'order_key':self.key,'amount':'1','transaction':details})
        self.assertEqual(self.fake.writes,[])

    def test_fully_gift_card_paid_order_still_offers_manual_actions(self):
        self.tool.ingest({'orders':[order(chargedAmount=0,giftCardAmount='30.19')]})
        listing=self.tool.listing('2026-10-01','2026-10-31')
        self.assertEqual(len(listing['orders']),1)
        self.assertEqual(listing['orders'][0]['basis'],'gift card (manual selection)')
        self.assertEqual(listing['orders'][0]['candidates'],[])
        self.assertEqual(listing['orders'][0]['payment']['amount'],'30.19')

    def test_manual_options_include_nonmatching_amounts_and_original_ids(self):
        options=self.tool.manual_options({'order_key':self.key,'start':'2026-10-01','end':'2026-10-31'})
        self.assertEqual([row['journal_id'] for row in options['journals']],['11','12','13'])
        self.assertTrue(all(row['group_id']=='100' and row['journal_count']==3 for row in options['journals']))
        self.assertTrue(options['gift_card_configured']);self.assertEqual(self.fake.writes,[])

    def test_multiple_paying_journals_in_one_split_parent_are_applied_together(self):
        before=copy.deepcopy(self.fake.groups['100'])
        plan=self.tool.manual_review({'order_key':self.key,'journal_ids':['12','13']})
        self.assertEqual(plan['total'],'20.00');self.assertEqual(self.fake.writes,[])
        result=self.tool.manual_apply({'plan_id':plan['id']});self.assertTrue(result['complete'])
        after=self.fake.groups['100']['attributes']
        self.assertEqual(after['group_title'],plan['description'])
        self.assertEqual(after['transactions'][0],before['attributes']['transactions'][0])
        self.assertTrue(all(row['description']==plan['description'] for row in after['transactions'][1:]))
        self.tool.manual_apply({'plan_id':plan['id']});self.assertEqual(len(self.fake.writes),1)

    def test_manual_stale_review_and_wrong_type_rejected(self):
        plan=self.tool.manual_review({'order_key':self.key,'journal_ids':['12']})
        self.fake.groups['100']['attributes']['transactions'][1]['amount']='14'
        with self.assertRaises(Problem):self.tool.manual_apply({'plan_id':plan['id']})
        with self.assertRaises(Problem):self.tool.manual_review({'order_key':self.key,'journal_ids':['21']})
        self.assertEqual(self.fake.writes,[])

    def test_gift_amount_and_copy_related_link_auditing_and_idempotency(self):
        before=copy.deepcopy(self.fake.groups['100'])
        plan=self.gift();self.assertEqual(plan['transaction']['amount'],'12.34');self.assertEqual(self.fake.writes,[])
        result=self.tool.gift_apply({'plan_id':plan['id']});self.assertEqual(result['group_id'],'300')
        self.assertEqual(self.fake.groups['100'],before)
        copy_journal=self.fake.groups['300']['attributes']['transactions'][0]
        for key in ('date','description','destination_id','currency_id','category_id'):
            self.assertEqual(copy_journal.get(key),before['attributes']['transactions'][0].get(key))
        self.assertEqual(copy_journal['source_id'],'9');self.assertIn('Gift Paid',copy_journal['tags'])
        self.assertEqual(self.fake.linkdata[0]['link_type_id'],'8')
        self.assertEqual({self.fake.linkdata[0]['inward_id'],self.fake.linkdata[0]['outward_id']},{'11','31'})
        self.tool.gift_apply({'plan_id':plan['id']});self.assertEqual(len(self.fake.writes),2)
        self.assertEqual({e['action'] for e in self.store.events()['events']},{'Create Amazon gift-card withdrawal','Relate Amazon gift-card withdrawal'})

    def test_lost_creation_and_link_responses_recover_without_duplicate(self):
        plan=self.gift();self.fake.lose_creation=True
        with self.assertRaises(Problem):self.tool.gift_apply({'plan_id':plan['id']})
        self.fake.lose_link_response=True
        with self.assertRaises(Problem):self.tool.gift_apply({'plan_id':plan['id']})
        self.assertTrue(self.tool.gift_apply({'plan_id':plan['id']})['complete'])
        self.assertEqual(len(self.fake.writes),2)

    def test_failed_creation_is_not_blindly_repeated(self):
        plan=self.gift();self.fake.reject_creation=True
        with self.assertRaises(Problem):self.tool.gift_apply({'plan_id':plan['id']})
        with self.assertRaises(Problem):self.tool.gift_apply({'plan_id':plan['id']})
        self.assertEqual(len(self.fake.writes),1)

    def test_amount_validation_and_foreign_proportion(self):
        for value in ('0','-1','NaN','0.001'):
            with self.assertRaises(Problem):self.gift(value)
        original=self.fake.groups['100']['attributes']['transactions'][0]
        original.update(foreign_currency_id='2',foreign_amount='60.00',foreign_currency_decimal_places=2)
        plan=self.gift('12.00');self.assertEqual(plan['transaction']['foreign_amount'],'24.00')
        self.tool.gift_apply({'plan_id':plan['id']})

    def test_submitted_copy_cannot_be_recreated_with_a_different_amount(self):
        first=self.gift('12.00');second=self.gift('13.00')
        self.tool.gift_apply({'plan_id':first['id']})
        with self.assertRaises(Problem):self.tool.gift_apply({'plan_id':second['id']})
        with self.assertRaises(Problem):self.gift('13.00')
        self.assertEqual(len(self.fake.writes),2)

    def test_manual_lost_write_response_is_recovered(self):
        plan=self.tool.manual_review({'order_key':self.key,'journal_ids':['12','13']})
        request=self.fake.request
        def lose(method,path,body=None,**params):
            result=request(method,path,body,**params)
            if method=='PUT':raise Problem('Lost update response',502)
            return result
        self.fake.request=lose
        with self.assertRaises(Problem):self.tool.manual_apply({'plan_id':plan['id']})
        self.assertTrue(self.tool.manual_apply({'plan_id':plan['id']})['complete'])
        self.assertEqual(len(self.fake.writes),1)

    def test_gift_stale_snapshot_and_unconfigured_account(self):
        plan=self.gift();self.fake.groups['100']['attributes']['transactions'][0]['tags'].append('new')
        with self.assertRaises(Problem):self.tool.gift_apply({'plan_id':plan['id']})
        with patch.dict(os.environ,{'AMAZON_GIFT_CARD_ACCOUNT_ID':''}):
            with self.assertRaises(Problem):self.gift()
        self.assertEqual(self.fake.writes,[])
