import copy
import threading
import unittest
from decimal import Decimal
from unittest.mock import patch
from sidecar.client import Problem
from sidecar.tools.validation import Validation
from test_reimbursements import FakeFirefly


class SplitFirefly(FakeFirefly):
    def request(self, method, path, body=None, **params):
        if method=='PUT' and path.startswith('transactions/'):
            body=copy.deepcopy(body)
            rows=self.groups[path.split('/')[1]]['attributes']['transactions']
            for item in body['transactions']:
                if 'transaction_journal_id' not in item:
                    item['transaction_journal_id']='99'
                    # Simulate Firefly creating a new journal from writable fields.
                    new=copy.deepcopy(item)
                    new['currency_code']='EUR'
                    rows.append(new)
        return super().request(method,path,body,**params)


class MarkReimbursementTests(unittest.TestCase):
    def setUp(self):
        self.client=SplitFirefly()
        self.tool=Validation(self.client,threading.Lock())
        row=self.client.groups['100']['attributes']['transactions'][0]
        row.update(tags=['todo','Personal'], budget_id='5',bill_id='6')

    def apply(self, mode='percent', value='50', jid='11'):
        token=self.tool.reimbursement_options({'journal_id':jid})['token']
        return self.tool.mark_reimbursement(dict(token=token,mode=mode,value=value))

    def test_partial_percentage_and_amount_preserve_total_description_and_siblings(self):
        for mode,value in [('percent','33.33'),('amount','10.00')]:
            with self.subTest(mode=mode):
                self.setUp()
                before=copy.deepcopy(self.client.groups['100'])
                result=self.apply(mode,value)
                rows=self.client.groups['100']['attributes']['transactions']
                self.assertEqual(sum(Decimal(r['amount']) for r in rows),Decimal('50'))
                self.assertEqual(rows[0]['description'],'My dinner')
                self.assertEqual(rows[0]['tags'],['Personal'])
                self.assertEqual(rows[0]['budget_id'],'5')
                self.assertEqual(rows[1:3],before['attributes']['transactions'][1:])
                self.assertEqual(rows[3]['description'],'Reimbursement')
                self.assertEqual(rows[3]['tags'],['Personal','Reimburse'])
                self.assertEqual(rows[3]['destination_id'],'7')
                self.assertIsNone(rows[3]['budget_id'])
                self.assertEqual(result['amount'],'10.00')
                self.assertEqual(self.client.groups['100']['attributes']['group_title'],'Dinner')
                payload=self.client.writes[0][2]
                self.assertFalse(payload['apply_rules'])
                self.assertFalse(payload['fire_webhooks'])

    def test_full_reimbursement_keeps_description_and_does_not_split(self):
        for mode,value in [('percent','100'),('amount','30')]:
            with self.subTest(mode=mode):
                self.setUp()
                result=self.apply(mode,value)
                self.assertFalse(result['partial'])
                rows=self.client.groups['100']['attributes']['transactions']
                self.assertEqual(len(rows),3)
                self.assertEqual(rows[0]['description'],'My dinner')
                self.assertEqual(rows[0]['tags'],['Personal','Reimburse'])
                self.assertEqual(rows[0]['destination_id'],'7')

    def test_unsplit_title_and_foreign_totals(self):
        rows=self.client.groups['100']['attributes']['transactions']
        rows[:]=rows[:1]
        self.client.groups['100']['attributes']['group_title']=None
        rows[0].update(foreign_amount='21.01',foreign_currency_id='2',foreign_currency_decimal_places=2)
        self.apply()
        self.assertEqual(self.client.groups['100']['attributes']['group_title'],'My dinner')
        self.assertEqual(sum(Decimal(r['foreign_amount']) for r in rows),Decimal('21.01'))

    def test_configured_tags_and_cash_todo_setting(self):
        with patch.dict('os.environ',{'MARK_CASH_REMOVE_TODO':'false','REIMBURSE_TAG':'Claim'}):
            self.tool=Validation(self.client,threading.Lock())
            self.apply(value='100')
        self.assertEqual(self.client.journal('11')[1]['tags'],['Personal','Claim'])

    def test_invalid_values_never_write(self):
        for mode,value in [('percent','0'),('percent','101'),('percent','NaN'),('amount','31'),('amount','0.001'),('amount','-1'),('bad','2'),('percent','0.001')]:
            with self.subTest(mode=mode,value=value):
                with self.assertRaises(Problem):self.apply(mode,value)
        self.assertEqual(self.client.writes,[])

    def test_stale_expired_and_replayed_previews_cannot_write(self):
        token=self.tool.reimbursement_options({'journal_id':'11'})['token']
        self.client.groups['100']['attributes']['transactions'][0]['description']='Changed'
        with self.assertRaises(Problem):self.tool.mark_reimbursement(dict(token=token,mode='percent',value='50'))
        self.assertEqual(self.client.writes,[])
        token=self.tool.reimbursement_options({'journal_id':'11'})['token']
        body=dict(token=token,mode='percent',value='50')
        self.tool.mark_reimbursement(body)
        with self.assertRaises(Problem):self.tool.mark_reimbursement(body)
        self.assertEqual(len(self.client.writes),1)

    def test_firefly_amount_formatting_does_not_fail_verification(self):
        original=self.client.request
        def formatted(method,path,body=None,**params):
            result=original(method,path,body,**params)
            if method=='PUT':
                for row in self.client.groups['100']['attributes']['transactions']:
                    row['amount']=format(Decimal(row['amount']),'.12f')
            return result
        self.client.request=formatted
        self.assertTrue(self.apply()['complete'])

    def test_verification_detects_wrong_total(self):
        original=self.client.request
        def corrupt(method,path,body=None,**params):
            result=original(method,path,body,**params)
            if method=='PUT':self.client.groups['100']['attributes']['transactions'][-1]['amount']='8'
            return result
        self.client.request=corrupt
        with self.assertRaises(Problem):self.apply()

    def test_all_siblings_validated_for_full_and_partial_reimbursements(self):
        for percentage in ('50','100'):
            self.setUp()
            rows=self.client.groups['100']['attributes']['transactions']
            for row in rows:row['tags']=['todo','Keep']
            before=copy.deepcopy(rows[1:])
            self.tool.cash_remove_todo=False
            self.apply(value=percentage)
            for row in rows:self.assertNotIn('todo',row['tags'])
            for row in before:row['tags']=['Keep']
            self.assertEqual(rows[1:3],before)

    def test_regular_split_preserves_tags_categorization_and_siblings(self):
        before=copy.deepcopy(self.client.groups['100'])
        token=self.tool.reimbursement_options({'journal_id':'11'})['token']
        result=self.tool.split_transaction({'token':token,'mode':'amount','value':'10','description':'My portion'})
        rows=self.client.groups['100']['attributes']['transactions']
        self.assertTrue(result['partial'])
        self.assertEqual(rows[0]['amount'],'20.00')
        self.assertEqual(rows[0]['tags'],['todo','Personal'])
        self.assertEqual(rows[1:3],before['attributes']['transactions'][1:])
        new=rows[-1]
        self.assertEqual(new['description'],'My portion')
        for field in ('source_id','destination_id','category_id','category_name','budget_id','bill_id','tags'):
            self.assertEqual(new.get(field),before['attributes']['transactions'][0].get(field))
        self.assertNotIn('Reimburse',new['tags'])
        self.assertEqual(sum(Decimal(row['amount']) for row in rows),Decimal('50'))

    def test_regular_split_rejects_full_amount_and_bad_description(self):
        token=self.tool.reimbursement_options({'journal_id':'11'})['token']
        for fields in ({'value':'100'},{'value':'50','description':''},{'value':'50','reimbursement':'yes'}):
            with self.assertRaises(Problem):self.tool.split_transaction(dict(token=token,mode='percent',**fields))
        self.assertEqual(self.client.writes,[])

    def test_split_reimbursement_option_keeps_existing_behavior(self):
        token=self.tool.reimbursement_options({'journal_id':'11'})['token']
        self.tool.split_transaction({'token':token,'mode':'percent','value':'50','reimbursement':True,'description':'Ignored'})
        row=self.client.groups['100']['attributes']['transactions'][-1]
        self.assertEqual(row['description'],'Reimbursement')
        self.assertEqual(row['destination_id'],'7')
        self.assertIn('Reimburse',row['tags'])
        self.assertTrue(all('todo' not in row['tags'] for row in self.client.groups['100']['attributes']['transactions']))
