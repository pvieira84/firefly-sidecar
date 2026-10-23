import copy
import threading
import unittest
from unittest.mock import patch
from sidecar.client import Problem
from sidecar.tools.validation import Validation
from test_reimbursements import FakeFirefly


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeFirefly()
        self.client.groups['100']['attributes']['transactions'][0]['tags'] = ['todo', 'Personal']
        self.client.groups['100']['attributes']['transactions'][1]['tags'] = ['Trip', 'todo', 'Reimburse']
        self.tool = Validation(self.client, threading.Lock())

    def test_listing_includes_categorized_and_uncategorized_journals(self):
        rows = self.tool.listing()['transactions']
        self.assertEqual({r['journal_id'] for r in rows}, {'11', '12'})
        self.assertEqual(next(r for r in rows if r['journal_id']=='11')['category_name'], 'Dining')

    def test_complete_preserves_siblings_finances_and_other_tags_and_retries(self):
        before = copy.deepcopy(self.client.groups)
        self.assertTrue(self.tool.complete({'journal_id':'12'})['complete'])
        self.assertEqual(self.client.journal('12')[1]['tags'], ['Trip', 'Reimburse'])
        before['100']['attributes']['transactions'][1]['tags'] = ['Trip', 'Reimburse']
        self.assertEqual(self.client.groups, before)
        payload = self.client.writes[0][2]
        self.assertEqual(payload['group_title'], 'Dinner')
        self.assertFalse(payload['apply_rules'])
        self.assertFalse(payload['fire_webhooks'])
        self.tool.complete({'journal_id':'12'})
        self.assertEqual(len(self.client.writes), 1)

    def test_unsplit_and_configured_tag(self):
        with patch.dict('os.environ', {'TODO_TAG':'#Review'}):
            tool = Validation(self.client, threading.Lock())
        row = self.client.groups['100']['attributes']['transactions'][0]
        row['tags'] = ['#Review','Keep']
        self.client.groups['100']['attributes']['transactions'] = [row]
        self.assertEqual(len(tool.listing()['transactions']), 1)
        tool.complete({'journal_id':'11'})
        self.assertEqual(self.client.journal('11')[1]['tags'], ['Keep'])
        self.assertNotIn('group_title', self.client.writes[0][2])

    def test_failed_write_keeps_tag_and_can_be_retried(self):
        self.client.fail_tag = True
        with self.assertRaises(Problem): self.tool.complete({'journal_id':'12'})
        self.assertIn('todo', self.client.journal('12')[1]['tags'])
        self.tool.complete({'journal_id':'12'})
        self.assertNotIn('todo', self.client.journal('12')[1]['tags'])

    def test_invalid_id_rejected_without_writes(self):
        with self.assertRaises(Problem): self.tool.complete({'journal_id':'../12'})
        self.assertEqual(self.client.writes, [])

    def test_delete_requires_preview_and_deletes_entire_group(self):
        with self.assertRaises(Problem): self.tool.delete({'token':'missing'})
        self.assertEqual(self.client.writes, [])
        preview=self.tool.delete_preview({'group_id':'100'})
        self.assertEqual(len(preview['transaction']['attributes']['transactions']),3)
        self.assertEqual(self.client.writes, [])
        result=self.tool.delete({'token':preview['token']})
        self.assertTrue(result['deleted'])
        self.assertNotIn('100',self.client.groups)
        self.assertIn('200',self.client.groups)
        self.assertEqual(self.client.writes,[('DELETE','transactions/100',None)])
        with self.assertRaises(Problem): self.tool.delete({'token':preview['token']})
        self.assertEqual(len(self.client.writes),1)

    def test_delete_candidate_without_todo_is_supported(self):
        preview=self.tool.delete_preview({'group_id':'200'})
        self.tool.delete({'token':preview['token']})
        self.assertNotIn('200',self.client.groups)
        self.assertIn('100',self.client.groups)

    def test_changed_or_expired_preview_does_not_delete(self):
        preview=self.tool.delete_preview({'group_id':'100'})
        self.client.groups['100']['attributes']['transactions'][0]['amount']='31.00'
        with self.assertRaises(Problem):self.tool.delete({'token':preview['token']})
        self.assertEqual(self.client.writes,[])
        preview=self.tool.delete_preview({'group_id':'100'})
        self.tool.deletion_previews[preview['token']]['created']-=601
        with self.assertRaises(Problem):self.tool.delete({'token':preview['token']})
        self.assertEqual(self.client.writes,[])

    def test_mark_cash_correct_direction_and_preservation_for_each_type(self):
        for kind in ('withdrawal','deposit','transfer'):
            with self.subTest(kind=kind):
                self.client=FakeFirefly()
                self.tool=Validation(self.client,threading.Lock())
                row=self.client.groups['100']['attributes']['transactions'][1]
                row.update(type=kind,category_id='5',category_name='Dining',budget_id='10',
                           budget_name='Dining budget',bill_id='3',bill_name='Subscription',tags=['todo','Trip'])
                before=copy.deepcopy(self.client.groups)
                self.assertTrue(self.tool.mark_cash({'journal_id':'12'})['complete'])
                verified=self.client.journal('12')[1]
                for key in ('category_id','category_name','budget_id','budget_name','bill_id','bill_name'):
                    self.assertIsNone(verified[key])
                self.assertEqual(verified['tags'],['Trip'])
                self.assertEqual(verified['amount'],'15.00')
                self.assertEqual(verified['source_id'],'7' if kind=='deposit' else '1')
                self.assertEqual(verified['destination_id'],'7' if kind=='withdrawal' else '2')
                for index in (0,2):
                    self.assertEqual(self.client.groups['100']['attributes']['transactions'][index],
                                     before['100']['attributes']['transactions'][index])
                payload=self.client.writes[0][2]
                self.assertEqual(payload['group_title'],'Dinner')
                self.assertFalse(payload['apply_rules']);self.assertFalse(payload['fire_webhooks'])
                patch=payload['transactions'][1]
                if kind=='transfer':
                    self.assertNotIn('source_id',patch);self.assertNotIn('destination_id',patch)

    def test_mark_cash_can_keep_todo_via_environment(self):
        from unittest.mock import patch
        with patch.dict('os.environ',{'MARK_CASH_REMOVE_TODO':'false'}):
            tool=Validation(self.client,threading.Lock())
        tool.mark_cash({'journal_id':'12'})
        self.assertEqual(self.client.journal('12')[1]['tags'],['Trip','todo','Reimburse'])
        with patch.dict('os.environ',{'MARK_CASH_REMOVE_TODO':'typo'}):
            with self.assertRaises(ValueError):Validation(self.client,threading.Lock())

    def test_already_cash_removes_configured_todo_and_is_idempotent(self):
        self.tool.tag='#Review'
        row=self.client.groups['100']['attributes']['transactions'][1]
        row.update(destination_id='7',category_id=None,category_name=None,budget_id=None,bill_id=None,tags=['Keep','#Review','todo'])
        self.tool.mark_cash({'journal_id':'12'})
        self.assertEqual(self.client.journal('12')[1]['tags'],['Keep','todo'])
        writes=len(self.client.writes)
        self.tool.mark_cash({'journal_id':'12'})
        self.assertEqual(len(self.client.writes),writes)

    def test_transfer_cash_does_not_need_cash_account_lookup(self):
        self.client.groups['100']['attributes']['transactions'][1]['type']='transfer'
        from unittest.mock import Mock
        self.client.all=Mock(side_effect=AssertionError('No account lookup expected'))
        self.tool.mark_cash({'journal_id':'12'})
        self.client.all.assert_not_called()

    def test_ambiguous_cash_account_prevents_write(self):
        self.client.all=lambda *args,**kwargs:[{'id':'7','attributes':{'type':'cash'}},{'id':'8','attributes':{'type':'cash'}}]
        with self.assertRaises(Problem):self.tool.mark_cash({'journal_id':'12'})
        self.assertEqual(self.client.writes,[])

    def test_cash_unsplit_supported_and_failed_updates_retry(self):
        row=self.client.groups['100']['attributes']['transactions'][1]
        self.client.groups['100']['attributes']['transactions']=[row]
        self.client.fail_tag=True
        with self.assertRaises(Problem):self.tool.mark_cash({'journal_id':'12'})
        self.assertEqual(self.client.journal('12')[1]['destination_id'],'2')
        self.tool.mark_cash({'journal_id':'12'})
        self.assertEqual(self.client.journal('12')[1]['destination_id'],'7')
        self.assertNotIn('group_title',self.client.writes[-1][2])
