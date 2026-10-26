import copy
import tempfile
import unittest
from pathlib import Path
from sidecar.client import Problem
from sidecar.store import Store
from sidecar.tools.reimbursements import Reimbursements


def split(jid, amount, kind='withdrawal', **kwargs):
    return dict(transaction_journal_id=jid, amount=amount, type=kind,
                date='2026-10-20T00:00:00+00:00', currency_code='EUR', currency_id='1',
                description='Reimbursement' if kind=='withdrawal' else 'Payment from Alex',
                category_id=None, category_name=None, tags=['Reimburse', 'Trip'] if kind=='withdrawal' else [],
                source_id='1', destination_id='2', source_name='Current account', destination_name='Restaurant', **kwargs)


class FakeFirefly:
    url = 'http://firefly.test'
    token = 'server-secret'

    def __init__(self):
        own = split('11', '30.00')
        own.update(description='My dinner', category_id='7', category_name='Dining', tags=['Personal'])
        self.groups = {
            '100': {'id': '100', 'attributes': {'group_title':'Dinner', 'transactions':[own, split('12','15.00'), split('13','5.00')]}},
            '200': {'id': '200', 'attributes': {'group_title':'', 'transactions':[split('21','20.00','deposit')]}}
        }
        self.linkdata=[]
        self.writes=[]
        self.fail_tag=False
        self.lose_link_response=False

    def journal(self, jid):
        for g in self.groups.values():
            for s in g['attributes']['transactions']:
                if s['transaction_journal_id']==jid:
                    return copy.deepcopy(g), copy.deepcopy(s)
        raise Problem('Missing split',404)

    def all(self, path, **params):
        if path=='link-types':
            return [{'id':'4','attributes':{'name':'Reimbursement','inward':'is (partially) reimbursed by','outward':'(partially) reimburses'}}, {'id':'5','attributes':{'name':'Refund','inward':'is (partially) refunded by','outward':'(partially) refunds'}}]
        if path.endswith('/links'):
            jid=path.split('/')[1]
            return [{'id':str(i),'attributes':copy.deepcopy(x)} for i,x in enumerate(self.linkdata) if jid in (x['inward_id'],x['outward_id'])]
        if path=='accounts': return [{'id':'7','attributes':{'type':'cash','name':'Cash account'}}]
        if path=='search/transactions': return [copy.deepcopy(self.groups['100'])]
        if path=='transactions': return [copy.deepcopy(self.groups['100' if params.get('type')=='withdrawal' else '200'])]
        if path.startswith('tags/'): return [copy.deepcopy(self.groups['100'])]
        raise AssertionError(path)

    def request(self, method, path, body=None, **params):
        if path=='about': return {'data':{'version':'test'}}
        if method=='GET' and path.startswith('transactions/'):
            return {'data':copy.deepcopy(self.groups[path.split('/')[1]])}
        self.writes.append((method,path,copy.deepcopy(body)))
        if method=='DELETE' and path.startswith('transactions/'):
            del self.groups[path.split('/')[1]]
            return {}
        if method=='PUT' and path.startswith('transaction-links/'):
            self.linkdata[int(path.split('/')[1])].update(copy.deepcopy(body))
            return {'data':{'id':path.split('/')[1]}}
        if path=='transaction-links':
            self.linkdata.append(copy.deepcopy(body))
            if self.lose_link_response:
                self.lose_link_response=False
                raise Problem('Connection lost after link write',502)
            return {'data':{'id':'1'}}
        if method=='PUT':
            if self.fail_tag:
                self.fail_tag=False
                raise Problem('Tag write failed',502)
            group=self.groups[path.split('/')[1]]
            if len(body['transactions']) > 1 and not body.get('group_title'):
                raise Problem('group_title: A group title is mandatory when there is more than one transaction.', 502)
            if 'group_title' in body:
                group['attributes']['group_title'] = body['group_title']
            # Match Firefly's identity-based update semantics.
            for patch in body['transactions']:
                for s in group['attributes']['transactions']:
                    if s['transaction_journal_id']==patch['transaction_journal_id']:
                        s.update({k:v for k,v in patch.items() if k!='transaction_journal_id'})
            return {'data':copy.deepcopy(group)}
        raise AssertionError((method,path))


class ReimbursementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.tmp.name)/'audit.sqlite3'))
        self.client=FakeFirefly()
        self.service=Reimbursements(self.client,self.store)

    def tearDown(self): self.tmp.cleanup()

    def review(self): return self.service.prepare({'deposit_id':'21','expense_ids':['12','13']})

    def test_candidates_are_individual_eligible_splits(self):
        rows=self.service.listing()
        self.assertEqual([x['journal_id'] for x in rows['expenses']],['12','13'])
        self.assertEqual(rows['expenses'][0]['group_title'],'Dinner')

    def test_multiple_tags_in_any_position_remain_visible_and_can_be_reviewed(self):
        for tags in (['Reimburse', 'Trip', 'Alex'], ['Trip', 'Reimburse', 'Alex'],
                     ['Trip', 'Alex', 'Reimburse']):
            with self.subTest(tags=tags):
                self.client.groups['100']['attributes']['transactions'][1]['tags'] = tags[:]
                rows = self.service.listing()['expenses']
                row = next(x for x in rows if x['journal_id'] == '12')
                self.assertEqual(row['tags'], tags)
                plan = self.review()
                self.assertEqual(plan['expenses'][0]['tags'], tags)

    def test_end_to_end_preserves_own_share_and_other_tags(self):
        original=copy.deepcopy(self.client.groups['100']['attributes']['transactions'][0])
        p=self.review()
        self.assertEqual(self.client.writes,[])
        result=self.service.apply(p['id'])
        self.assertTrue(result['complete'])
        self.assertEqual(len(self.client.linkdata),2)
        self.assertEqual(self.client.linkdata[0]['inward_id'],'21')
        self.assertEqual(self.client.linkdata[0]['outward_id'],'12')
        self.assertEqual(self.client.journal('12')[1]['tags'],['Trip'])
        self.assertEqual(self.client.journal('13')[1]['tags'],['Trip'])
        self.assertEqual(self.client.journal('11')[1],original)
        for method,path,body in self.client.writes:
            if method=='PUT':
                self.assertEqual(body['group_title'], 'Dinner')
                self.assertFalse(body['apply_rules'])
                self.assertFalse(body['fire_webhooks'])
                self.assertEqual(len(body['transactions']),3)
                self.assertEqual(set(body['transactions'][0]),{'transaction_journal_id'})
                self.assertEqual(sum('tags' in patch for patch in body['transactions']),1)
        self.assertEqual(self.service.listing()['expenses'],[])
        n=len(self.client.writes)
        self.service.apply(p['id'])
        self.assertEqual(len(self.client.writes),n)

    def test_unsplit_tag_update_does_not_require_group_title(self):
        reimbursement = self.client.groups['100']['attributes']['transactions'][1]
        self.client.groups['100']['attributes']['transactions'] = [reimbursement]
        self.client.groups['100']['attributes']['group_title'] = None
        plan = self.service.prepare({'deposit_id': '21', 'expense_ids': ['12']})
        self.assertTrue(self.service.apply(plan['id'])['complete'])
        update = next(body for method, path, body in self.client.writes if method == 'PUT')
        self.assertNotIn('group_title', update)
        self.assertEqual(self.client.journal('12')[1]['tags'], ['Trip'])

    def test_tag_failure_preserves_pending_tag_then_retry_deduplicates(self):
        p=self.review();self.client.fail_tag=True
        r=self.service.apply(p['id'])
        self.assertFalse(r['complete'])
        self.assertIn('Reimburse',self.client.journal('12')[1]['tags'])
        self.assertEqual(len(self.client.linkdata),1)
        # New service simulates a restart; the plan is durable.
        restarted=Reimbursements(self.client,Store(self.store.filename))
        self.assertTrue(restarted.apply(p['id'])['complete'])
        self.assertEqual(len(self.client.linkdata),2)

    def test_lost_link_response_recovered_without_duplicate(self):
        p=self.review();self.client.lose_link_response=True
        self.assertFalse(self.service.apply(p['id'])['complete'])
        self.assertIn('Reimburse',self.client.journal('12')[1]['tags'])
        self.assertTrue(self.service.apply(p['id'])['complete'])
        self.assertEqual(len(self.client.linkdata),2)

    def test_changed_expense_blocks_all_writes(self):
        p=self.review()
        self.client.groups['100']['attributes']['transactions'][2]['amount']='6.00'
        with self.assertRaises(Problem): self.service.apply(p['id'])
        self.assertEqual(self.client.writes,[])

    def test_changed_deposit_blocks_all_writes(self):
        p=self.review()
        self.client.groups['200']['attributes']['transactions'][0]['amount']='21.00'
        with self.assertRaises(Problem): self.service.apply(p['id'])
        self.assertEqual(self.client.writes,[])

    def test_mismatch_currency_and_duplicate_selection_rejected(self):
        for body in [{'deposit_id':'21','expense_ids':[]},
                     {'deposit_id':'21','expense_ids':['12','12']},
                     {'deposit_id':'12','expense_ids':['13']},
                     {'deposit_id':'../21','expense_ids':['12','13']}]:
            with self.assertRaises(Problem): self.service.prepare(body)
        self.client.groups['100']['attributes']['transactions'][1]['currency_code']='USD'
        with self.assertRaises(Problem): self.review()
        self.assertEqual(self.client.writes,[])

    def test_tag_and_withdrawal_type_required(self):
        for field,value in [('type','deposit'),('tags',['Other'])]:
            old=self.client.groups['100']['attributes']['transactions'][1][field]
            self.client.groups['100']['attributes']['transactions'][1][field]=value
            with self.assertRaises(Problem): self.review()
            self.client.groups['100']['attributes']['transactions'][1][field]=old

    def test_tagged_uncategorized_withdrawals_ignore_description(self):
        for description in ('Reimbursement for dinner', 'CRV*BOLTEUO2610081735 / MCC: 4121', '', None):
            with self.subTest(description=description):
                self.client.groups['100']['attributes']['transactions'][1]['description'] = description
                self.assertIn('12', [x['journal_id'] for x in self.service.listing()['expenses']])
                self.review()

    def test_single_reimbursement_can_be_reviewed_with_different_total(self):
        plan = self.service.prepare({'deposit_id': '21', 'expense_ids': ['12']})
        self.assertEqual(plan['total'], '15.00')
        self.assertEqual(plan['difference'], '5.00')
        self.assertTrue(self.service.apply(plan['id'])['complete'])
        self.assertEqual(self.client.journal('13')[1]['tags'], ['Reimburse', 'Trip'])

    def test_different_totals_can_be_reviewed_and_applied(self):
        for deposit_amount, difference in (('25.00', '5.00'), ('10.00', '-10.00')):
            with self.subTest(deposit=deposit_amount):
                self.client = FakeFirefly()
                self.service = Reimbursements(self.client, self.store)
                self.client.groups['200']['attributes']['transactions'][0]['amount'] = deposit_amount
                original = copy.deepcopy(self.client.groups)
                plan = self.review()
                self.assertEqual(plan['total'], '20.00')
                self.assertEqual(plan['difference'], difference)
                self.assertEqual(self.client.writes, [])
                self.assertTrue(self.service.apply(plan['id'])['complete'])
                self.assertEqual(len(self.client.linkdata), 2)
                self.assertEqual(self.client.journal('12')[1]['tags'], ['Trip'])
                self.assertEqual(self.client.journal('13')[1]['tags'], ['Trip'])
                self.assertEqual(self.client.groups['200'], original['200'])
                self.assertEqual(self.client.groups['100']['attributes']['transactions'][0],
                                 original['100']['attributes']['transactions'][0])

    def test_existing_reimbursement_deposit_rejected(self):
        self.client.linkdata=[{'link_type_id':'4','inward_id':'999','outward_id':'21'}]
        with self.assertRaises(Problem): self.review()
        self.assertEqual(self.client.writes,[])

    def test_conflicting_link_added_after_review_blocks_writes(self):
        p=self.review()
        self.client.linkdata=[{'link_type_id':'4','inward_id':'12','outward_id':'99'}]
        with self.assertRaises(Problem): self.service.apply(p['id'])
        self.assertEqual(self.client.writes,[])

    def test_untagged_without_expected_link_blocks_recovery(self):
        p=self.review()
        self.client.groups['100']['attributes']['transactions'][1]['tags']=[]
        with self.assertRaises(Problem): self.service.apply(p['id'])
        self.assertEqual(self.client.writes,[])

    def test_partial_legacy_links_corrected_in_place_on_retry(self):
        plan=self.review()
        self.client.linkdata=[{'link_type_id':'4','inward_id':'12','outward_id':'21',
                              'notes':'Firefly Sidecar review '+plan['id']}]
        self.assertTrue(self.service.apply(plan['id'])['complete'])
        self.assertEqual(len(self.client.linkdata),2)
        self.assertEqual(self.client.linkdata[0]['inward_id'],'21')
        self.assertEqual(self.client.linkdata[0]['outward_id'],'12')
        self.assertEqual(sum(method=='PUT' and path.startswith('transaction-links/') for method,path,_ in self.client.writes),1)

    def test_completed_legacy_links_can_be_corrected_without_repeating_tag_writes(self):
        plan=self.review()
        self.service.apply(plan['id'])
        for link in self.client.linkdata:
            link['inward_id'],link['outward_id']=link['outward_id'],link['inward_id']
        self.client.writes=[]
        self.assertTrue(self.service.apply(plan['id'])['complete'])
        self.assertEqual(len(self.client.linkdata),2)
        self.assertTrue(all(link['inward_id']=='21' for link in self.client.linkdata))
        self.assertTrue(all(method=='PUT' and path.startswith('transaction-links/') for method,path,_ in self.client.writes))
        self.assertEqual(len(self.client.writes),2)
        self.client.writes=[]
        self.assertTrue(self.service.apply(plan['id'])['complete'])
        self.assertEqual(self.client.writes,[])

    def test_reversed_links_from_other_operations_block_repair(self):
        plan=self.review()
        self.client.linkdata=[{'link_type_id':'4','inward_id':'12','outward_id':'21',
                              'notes':'Firefly Sidecar review someone-else'}]
        with self.assertRaises(Problem):self.service.apply(plan['id'])
        self.assertEqual(self.client.writes,[])

    def test_duplicate_legacy_and_correct_links_block_all_writes(self):
        plan=self.review()
        self.client.linkdata=[{'link_type_id':'4','inward_id':a,'outward_id':b,
                              'notes':'Firefly Sidecar review '+plan['id']}
                             for a,b in [('12','21'),('21','12')]]
        with self.assertRaises(Problem):self.service.apply(plan['id'])
        self.assertEqual(self.client.writes,[])

    def test_direction_correction_is_audited(self):
        from sidecar.auditing import AuditedFirefly
        plan=self.review()
        self.client.linkdata=[{'link_type_id':'4','inward_id':'12','outward_id':'21',
                              'notes':'Firefly Sidecar review '+plan['id']}]
        service=Reimbursements(AuditedFirefly(self.client,self.store),self.store)
        self.assertTrue(service.apply(plan['id'])['complete'])
        events=self.store.events()['events']
        corrections=[event for event in events if event['action']=='Correct reimbursement link direction']
        self.assertEqual(len(corrections),1)
        self.assertEqual(corrections[0]['state'],'completed')

    def test_decimal_totals_are_exact(self):
        self.client.groups['100']['attributes']['transactions'][1]['amount']='0.10'
        self.client.groups['100']['attributes']['transactions'][2]['amount']='0.20'
        self.client.groups['200']['attributes']['transactions'][0]['amount']='0.30'
        self.assertEqual(self.review()['total'],'0.30')


    def test_tag_search_has_no_history_scan_or_per_parent_fetches(self):
        original_all=self.client.all;calls=[]
        def searched(path,**params):
            calls.append((path,params))
            if path=='search/transactions':
                group=copy.deepcopy(self.client.groups['100'])
                return [group,copy.deepcopy(group)]
            if path=='transactions' and params.get('type')=='withdrawal':
                raise AssertionError('Must not scan withdrawal history')
            return original_all(path,**params)
        self.client.all=searched
        original_request=self.client.request
        def no_parent_fetch(method,path,body=None,**params):
            if method=='GET' and path.startswith('transactions/'):
                raise AssertionError('Must not fetch each parent during listing')
            return original_request(method,path,body,**params)
        self.client.request=no_parent_fetch
        rows=self.service.listing()['expenses']
        self.assertEqual([row['journal_id'] for row in rows],['12','13'])
        self.assertTrue(all(row['group_id']=='100' and row['journal_count']==3 for row in rows))
        self.assertIn(('search/transactions',{'query':'type:withdrawal tag:"Reimburse"'}),calls)
        self.assertEqual(self.client.writes,[])

    def test_zero_category_id_is_uncategorized_for_listing_and_review(self):
        self.client.groups['100']['attributes']['transactions'][1]['category_id']='0'
        self.assertIn('12',[row['journal_id'] for row in self.service.listing()['expenses']])
        self.assertEqual(len(self.review()['expenses']),2)

    def test_tag_endpoint_omitting_split_parent_does_not_hide_reimbursements(self):
        original_all=self.client.all
        def missing_parent(path,**params):
            if path.startswith('tags/'):return []
            return original_all(path,**params)
        self.client.all=missing_parent
        rows=self.service.listing(start='2026-10-25',end='2026-10-26')['expenses']
        self.assertEqual([row['journal_id'] for row in rows],['12','13'])
        self.assertTrue(all(row['journal_count']==3 for row in rows))
        self.assertEqual(len(self.review()['expenses']),2)

    def test_tagged_categorized_split_is_visible_and_reviewable(self):
        row=self.client.groups['100']['attributes']['transactions'][1]
        row.update(category_id='7',category_name='Dining')
        matches=self.service.listing()['expenses']
        self.assertIn('12',[match['journal_id'] for match in matches])
        self.assertEqual(len(self.review()['expenses']),2)

if __name__=='__main__': unittest.main()
