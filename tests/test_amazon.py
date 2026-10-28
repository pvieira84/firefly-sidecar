import copy
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from sidecar.tools.amazon import Amazon, description, marker, markdown_text
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

    def test_edited_review_notes_are_saved_verbatim_and_retries_use_same_text(self):
        self.ingest(order());plan=self.review()
        before=copy.deepcopy(self.fake.groups['100'])
        edited='Custom notes <text>\nSecond line'
        self.tool.apply({'plan_id':plan['id'],'notes':edited})
        after=self.fake.groups['100']
        expected=copy.deepcopy(before)
        expected['attributes']['group_title']=plan['group_title']
        expected['attributes']['transactions'][0].update(notes=edited,description=plan['description'])
        self.assertEqual(after,expected)
        saved,state,_=self.store.operation(plan['id'],'amazon')
        self.assertEqual(saved['notes'],edited);self.assertEqual(state,'complete')
        count=len(self.fake.writes)
        self.assertTrue(self.tool.apply({'plan_id':plan['id'],'notes':edited})['complete'])
        self.assertEqual(len(self.fake.writes),count)
        with self.assertRaises(Problem):self.tool.apply({'plan_id':plan['id'],'notes':'Different after submission'})
        self.assertEqual(len(self.fake.writes),count)

    def test_invalid_edited_notes_do_not_write_and_empty_notes_are_allowed(self):
        self.ingest(order());plan=self.review()
        for notes in (None,123,'x'*60001):
            with self.assertRaises(Problem):self.tool.apply({'plan_id':plan['id'],'notes':notes})
        self.assertEqual(self.fake.writes,[])
        self.tool.apply({'plan_id':plan['id'],'notes':''})
        self.assertEqual(self.fake.journal('11')[1]['notes'],'')

    def test_review_fetches_only_selected_journal_with_172_stored_orders(self):
        self.ingest(*[dict(order(),orderId=f'123-1234567-{i:07d}') for i in range(172)])
        selected=self.listing()['orders'][0]
        request={'key':selected['key'],'journal_id':'11','start':'2026-01-02','end':'2026-10-28'}
        with patch.object(self.tool,'listing',side_effect=AssertionError('Full matching search repeated')), \
             patch.object(self.tool,'orders',side_effect=AssertionError('All stored orders loaded')), \
             patch.object(self.tool.client,'all',side_effect=AssertionError('Firefly collection queried')), \
             patch.object(self.tool.client,'journal',wraps=self.tool.client.journal) as journal:
            plan=self.tool.review(request)
        journal.assert_called_once_with('11')
        self.assertEqual(plan['order']['key'],selected['order']['key'])
        self.assertEqual(plan['candidate']['journal_count'],3)
        self.assertEqual(len(plan['before']['attributes']['transactions']),3)
        self.assertEqual(self.fake.writes,[])

    def test_targeted_review_rechecks_live_match_eligibility(self):
        self.ingest(order());entry=self.listing()['orders'][0]
        request={'key':entry['key'],'journal_id':'11','start':'2026-10-01','end':'2026-10-31'}
        row=self.fake.groups['100']['attributes']['transactions'][0]
        for changes in ({'amount':'31'},{'currency_code':'USD'},{'type':'transfer'},
                        {'date':'2026-09-01'},{'description':'Unrelated purchase','destination_name':'Shop'}):
            before=dict(row);row.update(changes)
            with self.assertRaises(Problem):self.tool.review(request)
            row.clear();row.update(before)
        for changes in ({'key':'missing:payment:0'},{'key':None},{'days':'bad'},{'days':'61'},
                        {'start':'2026-10-25'},{'start':'2026-11-01'}):
            with self.assertRaises(Problem):self.tool.review(dict(request,**changes))
        with self.store.db() as db:db.execute('INSERT INTO amazon_matches VALUES (?,?)',('another:payment','11'))
        with self.assertRaises(Problem):self.tool.review(request)
        self.assertEqual(self.fake.writes,[])

    def test_inbox_dates_and_enriched_flag(self):
        self.ingest(order(transactions=[{'date':'2026-10-23','amount':'30'}]))
        status=self.tool.status()
        self.assertEqual((status['start'],status['end']),('2026-10-20','2026-10-23'))
        self.assertFalse(self.listing()['orders'][0]['enriched'])
        plan=self.review();self.tool.apply({'plan_id':plan['id']})
        self.assertTrue(self.listing()['orders'][0]['enriched'])
        self.assertNotEqual(self.tool.status()['revision'],status['revision'])
        self.assertEqual(self.tool.status()['not_enriched'],0)

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

    def test_explicit_charge_excludes_gift_transaction_and_keeps_charge_date(self):
        raw=order(chargedAmount='4.57',giftCardAmount='30.19',transactions=[
            {'date':'2026-10-20','amount':'30.19'}, {'date':'2026-10-21','amount':'4.57'}])
        raw['totalAmount']='4.57'
        self.ingest(raw)
        self.fake.groups['100']['attributes']['transactions'][0]['amount']='4.57'
        rows=self.listing()['orders']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['payment'],{'date':'2026-10-21','amount':'4.57'})
        self.assertEqual(rows[0]['basis'],'charged amount')
        self.assertEqual(rows[0]['display_total'],'34.76')
        self.assertEqual(rows[0]['order']['giftCardAmount'],'30.19')
        self.assertEqual(len(rows[0]['candidates']),1)
        self.ingest(order(chargedAmount='30',giftCardAmount=0,transactions=[{'date':'2026-10-20','amount':'99'}]))
        self.assertEqual(self.listing()['orders'][0]['payment']['amount'],'30')

    def test_review_apply_preserves_splits_and_audits_and_retry_is_idempotent(self):
        self.ingest(order());before=copy.deepcopy(self.fake.groups['100'])
        plan=self.review();self.assertEqual(self.fake.writes,[])
        result=self.tool.apply({'plan_id':plan['id']});self.assertTrue(result['complete'])
        after=copy.deepcopy(self.fake.groups['100'])
        notes=after['attributes']['transactions'][0].pop('notes')
        before['attributes']['transactions'][0].pop('notes')
        before['attributes']['transactions'][0]['description']='Amazon 123-1234567-1234567: 2x Coffee <beans>'
        before['attributes']['group_title']=before['attributes']['transactions'][0]['description']
        self.assertEqual(after,before);self.assertIn('Original note',notes);self.assertIn(markdown_text('Coffee <beans>'),notes)
        self.tool.apply({'plan_id':plan['id']});self.assertEqual(len(self.fake.writes),1)
        self.assertEqual(self.store.events()['events'][0]['action'],'Enrich Amazon order')
        self.assertEqual(self.store.events()['events'][0]['state'],'completed')
        self.assertTrue(self.listing()['orders'][0]['candidates'][0]['applied'])

    def test_description_matches_toolbox_and_notes_do_not_expose_account(self):
        raw=order();raw['items']=[{'title':'X'*60,'quantity':2},{'title':'Coffee','quantity':1}]
        self.tool.ingest({'account':'private-label','orders':[raw]})
        plan=self.review()
        self.assertEqual(plan['description'],'Amazon 123-1234567-1234567: 2x '+'X'*47+'..., Coffee')
        self.assertNotIn('private-label',plan['notes'])
        self.assertNotIn('amazon.es:',plan['notes'])
        self.tool.apply({'plan_id':plan['id']})
        self.assertEqual(self.fake.groups['100']['attributes']['transactions'][0]['description'],plan['description'])

    def test_legacy_note_marker_is_replaced_without_duplicate_items(self):
        self.tool.ingest({'account':'private-label','orders':[order()]})
        entry=self.listing()['orders'][0]
        old='[Sidecar Amazon '+entry['key']+']'
        self.fake.groups['100']['attributes']['transactions'][0]['notes']=old+'\nAmazon.es order 123-1234567-1234567\n2 × Coffee <beans>\nhttps://www.amazon.es/gp/your-account/order-details?orderID=123-1234567-1234567\n\nUser comment'
        plan=self.review()
        self.assertNotIn('private-label',plan['notes'])
        self.assertEqual(plan['notes'].count(markdown_text('Coffee <beans>')),1)
        self.assertIn(marker(entry['key']),plan['notes'])
        self.assertTrue(plan['notes'].endswith('User comment'))
        self.tool.apply({'plan_id':plan['id']})
        self.assertTrue(self.listing()['orders'][0]['candidates'][0]['applied'])

    def test_exact_notes_format_and_split_title_upgrade(self):
        raw=order();raw['items'].append({'title':'Tea','quantity':1})
        self.ingest(raw);plan=self.review()
        expected=marker(plan['key'])+'  \nAmazon Order 123-1234567-1234567  \nItems:\n- 2 x '+markdown_text('Coffee <beans>')+'\n- 1 x Tea\n\n[View Amazon order](https://www.amazon.es/gp/your-account/order-details?orderID=123-1234567-1234567)'
        self.assertEqual(plan['notes'],'Original note\n\n'+expected)
        self.assertEqual(plan['group_title'],plan['description'])
        self.tool.apply({'plan_id':plan['id']})
        self.assertEqual(self.fake.groups['100']['attributes']['group_title'],plan['description'])
        self.assertEqual(self.fake.groups['100']['attributes']['transactions'][1]['description'],'Reimbursement')
        # Matching notes/description alone do not skip a required parent-title update.
        self.fake.groups['100']['attributes']['group_title']='Old title'
        self.assertFalse(self.listing()['orders'][0]['candidates'][0]['applied'])
        plan=self.review();self.tool.apply({'plan_id':plan['id']})
        self.assertEqual(self.fake.groups['100']['attributes']['group_title'],plan['description'])

    def test_old_spaced_notes_upgrade_to_compact_linked_format(self):
        self.ingest(order());entry=self.listing()['orders'][0]
        old=marker(entry['key'])+'\n\nAmazon Order 123-1234567-1234567\n\nItems:\n\n• 2 x Coffee <beans>'
        self.fake.groups['100']['attributes']['transactions'][0]['notes']='User note\n\n'+old+'\n\nUser suffix'
        plan=self.review()
        self.assertEqual(plan['notes'].count(markdown_text('Coffee <beans>')),1)
        self.assertEqual(plan['notes'].count('[View Amazon order]'),1)
        self.assertIn('Items:\n- 2 x Coffee',plan['notes'])
        self.assertTrue(plan['notes'].endswith('User suffix'))
        self.tool.apply({'plan_id':plan['id']})
        self.assertEqual(self.review()['notes'],plan['notes'])

    def test_compact_literal_bullets_upgrade_to_markdown_without_duplicates(self):
        self.ingest(order());entry=self.listing()['orders'][0]
        old=marker(entry['key'])+'\nAmazon Order 123-1234567-1234567\nItems:\n• 2 x Coffee <beans>\n\n[View Amazon order](https://www.amazon.es/gp/your-account/order-details?orderID=123-1234567-1234567)'
        self.fake.groups['100']['attributes']['transactions'][0]['notes']='User prefix\n\n'+old+'\n\nUser suffix'
        plan=self.review()
        self.assertIn(marker(entry['key'])+'  \nAmazon Order 123-1234567-1234567  \nItems:\n- ',plan['notes'])
        self.assertEqual(plan['notes'].count('[View Amazon order]'),1)
        self.assertEqual(plan['notes'].count(markdown_text('Coffee <beans>')),1)
        self.assertTrue(plan['notes'].endswith('User suffix'))
        self.tool.apply({'plan_id':plan['id']})
        self.assertEqual(self.review()['notes'],plan['notes'])

    def test_product_markdown_is_literal_text(self):
        self.assertEqual(markdown_text('[Tea](https://example.test) <strong> & *coffee*'),r'\[Tea\](https://example.test) \<strong\> &amp; \*coffee\*')

    def test_order_count_is_unique_across_imports_and_does_not_read_firefly(self):
        self.assertEqual(self.tool.status()['stored'],0)
        self.ingest(order());self.ingest(order())
        self.assertEqual(self.tool.status()['stored'],1)
        self.assertEqual(self.fake.writes,[])

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

    def test_background_matching_routes_csrf_and_completion(self):
        import time
        self.assertEqual(self.req('/api/amazon/find-matches',{'start':'2026-10-01','end':'2026-10-31'})[0],403)
        _,body,_=self.req('/api/bootstrap');headers={'X-Sidecar-CSRF':json.loads(body)['csrf']}
        status,body,_=self.req('/api/amazon/find-matches',{'start':'2026-10-01','end':'2026-10-31'},**headers)
        self.assertEqual(status,200);jid=json.loads(body)['id']
        deadline=time.monotonic()+2
        while True:
            status,body,_=self.req('/api/amazon/match-status?id='+jid);result=json.loads(body)
            self.assertEqual(status,200)
            if result['state']!='running' or time.monotonic()>deadline:break
            time.sleep(.01)
        self.assertEqual(result['state'],'complete')
        self.assertEqual(result['result']['not_enriched'],0)
        self.assertEqual(self.req('/api/amazon/match-status?id=missing')[0],404)
        self.assertEqual(self.client.writes,[])

    def test_count_endpoint_and_bootstrap_include_received_orders(self):
        status,body,_=self.req('/api/amazon/status')
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['stored'],0)
        store=Store(self.tmp.name+'/test.db')
        Amazon(self.client,store,threading.RLock()).ingest({'orders':[order()]})
        self.assertEqual(json.loads(self.req('/api/amazon/status')[1])['stored'],1)
        bootstrap=json.loads(self.req('/api/bootstrap')[1])
        self.assertEqual(bootstrap['amazon_order_count'],1)
        self.assertEqual(bootstrap['amazon_pending_count'],1)
        self.assertEqual(self.client.writes,[])

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
