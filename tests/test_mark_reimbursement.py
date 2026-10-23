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
                self.assertEqual(rows[0]['tags'],['todo','Personal'])
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
        self.assertEqual(self.client.journal('11')[1]['tags'],['todo','Personal','Claim'])

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
