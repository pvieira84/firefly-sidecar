import copy
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from sidecar.tools.amazon import Amazon
from sidecar.store import Store
from sidecar.client import Problem
from sidecar.auditing import AuditedFirefly
from test_reimbursements import FakeFirefly
import test_http


def order(**changes):
    return dict(orderId='123-1234567-1234567', orderDate='2026-10-20', totalAmount='30.00', currency='EUR',
                items=[{'title':'Coffee <beans>', 'quantity':2, 'asin':'B123456789'}], **changes)


class AmazonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name+'/test.db')
        self.fake = FakeFirefly()
        self.fake.groups['100']['attributes']['transactions'][0].update(description='Amazon purchase', notes='Original note')
        self.tool = Amazon(AuditedFirefly(self.fake,self.store),self.store,threading.RLock())

    def tearDown(self): self.tmp.cleanup()

    def ingest(self, *orders): return self.tool.ingest({'orders':list(orders)})
    def listing(self): return self.tool.listing('2026-10-01','2026-10-31')
    def review(self):
        entry=self.listing()['orders'][0]
        return self.tool.review({'key':entry['key'],'journal_id':'11','start':'2026-10-01','end':'2026-10-31'})

    def test_import_deduplicates_and_discards_personal_fields(self):
        raw=order(recipientStreet='Private address')
        self.ingest(raw);self.ingest(raw)
        self.assertEqual(len(self.tool.orders()),1)
        self.assertNotIn('Private address',json.dumps(self.tool.orders()))
        self.assertEqual(self.fake.writes,[])

    def test_payment_amount_not_order_total_refunds_not_matched(self):
        self.ingest(order(transactions=[{'date':'2026-10-20','amount':30,'currency':'EUR'}, {'date':'2026-10-21','amount':-30,'currency':'EUR'}]))
        rows=self.listing()['orders'];self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['basis'],'payment');self.assertEqual(len(rows[0]['candidates']),1)
        self.ingest(order(chargedAmount='15'))
        self.assertFalse(self.listing()['orders'][0]['candidates'])

    def test_review_apply_preserves_splits_and_audits_and_retry_is_idempotent(self):
        self.ingest(order());before=copy.deepcopy(self.fake.groups['100'])
        plan=self.review();self.assertEqual(self.fake.writes,[])
        result=self.tool.apply({'plan_id':plan['id']});self.assertTrue(result['complete'])
        after=copy.deepcopy(self.fake.groups['100'])
        notes=after['attributes']['transactions'][0].pop('notes')
        before['attributes']['transactions'][0].pop('notes')
        self.assertEqual(after,before);self.assertIn('Original note',notes);self.assertIn('Coffee <beans>',notes)
        self.tool.apply({'plan_id':plan['id']});self.assertEqual(len(self.fake.writes),1)
        self.assertEqual(self.store.events()['events'][0]['action'],'Enrich Amazon order')
        self.assertEqual(self.store.events()['events'][0]['state'],'completed')
        self.assertTrue(self.listing()['orders'][0]['candidates'][0]['applied'])

    def test_stale_transaction_and_order_block_writes(self):
        self.ingest(order());plan=self.review()
        self.fake.groups['100']['attributes']['transactions'][0]['tags'].append('changed')
        with self.assertRaises(Problem):self.tool.apply({'plan_id':plan['id']})
        plan=self.review()
        raw=order();raw['items']=[];self.ingest(raw)
        with self.assertRaises(Problem):self.tool.apply({'plan_id':plan['id']})
        self.assertEqual(self.fake.writes,[])

    def test_one_payment_cannot_enrich_two_journals(self):
        self.fake.groups['100']['attributes']['transactions'][1].update(amount='30',description='Amazon other')
        self.ingest(order());first=self.review();second=self.tool.review({'key':first['key'],'journal_id':'12','start':'2026-10-01','end':'2026-10-31'})
        self.tool.apply({'plan_id':first['id']})
        with self.assertRaises(Problem):self.tool.apply({'plan_id':second['id']})
        self.assertEqual(len(self.fake.writes),1)

    def test_lost_response_recovers_without_duplicate_write(self):
        self.ingest(order());plan=self.review()
        request=self.fake.request
        def lose(method,path,body=None,**params):
            result=request(method,path,body,**params)
            if method=='PUT':raise Problem('Lost response',502)
            return result
        self.fake.request=lose
        with self.assertRaises(Problem):self.tool.apply({'plan_id':plan['id']})
        self.assertEqual(self.store.events()['events'][0]['state'],'uncertain')
        self.assertTrue(self.tool.apply({'plan_id':plan['id']})['complete'])
        self.assertEqual(len(self.fake.writes),1)

    def test_validation_is_atomic_and_rejects_bad_amount(self):
        for amount in ('NaN','Infinity','-1',None):
            raw=order();raw['totalAmount']=amount
            with self.assertRaises(Problem):self.ingest(order(),raw)
        self.assertEqual(self.tool.orders(),[])

    def test_payment_keys_survive_new_earlier_payments_and_decimal_format(self):
        self.ingest(order(transactions=[{'date':'2026-10-20','amount':'30.00'}]))
        key=self.listing()['orders'][0]['key']
        self.ingest(order(transactions=[{'date':'2026-10-19','amount':'1'}, {'date':'2026-10-20','amount':30}]))
        self.assertEqual(key,self.listing()['orders'][1]['key'])


class AmazonHttpTests(unittest.TestCase):
    setUp = test_http.HttpTests.setUp
    tearDown = test_http.HttpTests.tearDown
    req = test_http.HttpTests.req

    def test_extension_import_token_is_scoped_and_host_checked(self):
        from sidecar.server import make_handler
        token='x'*40
        with patch.dict(os.environ,{'AMAZON_SYNC_TOKEN':token,'SIDECAR_PASSWORD':'password','SIDECAR_HOSTS':'127.0.0.1'}):
            self.server.RequestHandlerClass=make_handler(self.client,Store(self.tmp.name+'/amazon.db'))
        payload={'orders':[order()]}
        self.assertEqual(self.req('/api/amazon/import',payload)[0],403)
        self.assertEqual(self.req('/api/amazon/import',payload,Authorization='Bearer '+token)[0],200)
        self.assertEqual(self.req('/api/amazon/apply',{'plan_id':'bad'},Authorization='Bearer '+token)[0],401)
        self.assertEqual(self.req('/api/amazon/import',payload,Authorization='Bearer '+token,Host='evil.example')[0],403)
