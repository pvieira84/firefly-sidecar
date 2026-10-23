import tempfile
import threading
import unittest
from unittest.mock import Mock
from sidecar.auditing import AuditedFirefly
from sidecar.store import Store
from sidecar.client import Problem
from sidecar.tools.validation import Validation
from sidecar.tools.reimbursements import Reimbursements
from test_reimbursements import FakeFirefly


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(self.tmp.name+'/audit.db')
        self.raw=FakeFirefly()
        self.client=AuditedFirefly(self.raw,self.store)

    def tearDown(self): self.tmp.cleanup()

    def test_tag_change_records_before_after_and_survives_restart(self):
        self.raw.groups['100']['attributes']['transactions'][0]['tags']=['todo','Personal']
        tool=Validation(self.client,threading.Lock())
        tool.complete({'journal_id':'11'})
        event=Store(self.store.filename).events()['events'][0]
        self.assertEqual(event['state'],'completed')
        self.assertEqual(event['group_id'],'100')
        self.assertEqual(event['tag_changes'][0]['before'],['todo','Personal'])
        self.assertEqual(event['tag_changes'][0]['after'],['Personal'])
        self.assertEqual(event['before']['attributes']['transactions'][0]['tags'],['todo','Personal'])
        self.assertEqual(event['after']['attributes']['transactions'][0]['tags'],['Personal'])
        tool.complete({'journal_id':'11'})
        self.assertEqual(len(self.store.events()['events']),1)

    def test_delete_preserves_snapshot(self):
        tool=Validation(self.client,threading.Lock())
        preview=tool.delete_preview({'group_id':'100'})
        self.assertEqual(self.store.events()['events'],[])
        tool.delete({'token':preview['token']})
        event=self.store.events()['events'][0]
        self.assertEqual(event['action'],'Delete transaction')
        self.assertEqual(len(event['before']['attributes']['transactions']),3)
        self.assertIsNone(event['after'])

    def test_reimbursement_records_each_link_and_tag_write(self):
        tool=Reimbursements(self.client,self.store)
        plan=tool.prepare({'deposit_id':'21','expense_ids':['12','13']})
        self.assertEqual(self.store.events()['events'][0]['entry_type'],'reimbursement')
        self.assertEqual(self.raw.writes,[])
        tool.apply(plan['id'])
        timeline=self.store.events()['events']
        summary=next(event for event in timeline if event.get('entry_type')=='reimbursement')
        self.assertEqual(summary['state'],'completed')
        events=[event for event in timeline if event.get('entry_type')!='reimbursement']
        self.assertEqual(len(events),4)
        self.assertTrue(all(e['state']=='completed' for e in events))
        self.assertEqual(sum(e['action']=='Create reimbursement link' for e in events),2)

    def test_lost_response_is_uncertain_and_retry_is_separate(self):
        self.raw.fail_tag=True
        with self.assertRaises(Problem):self.client.request('PUT','transactions/100',{'transactions':[]})
        self.assertEqual(self.store.events()['events'][0]['state'],'uncertain')
        self.client.request('PUT','transactions/100',{'transactions':[]})
        self.assertEqual({e['state'] for e in self.store.events()['events']},{'completed','uncertain'})

    def test_failure_to_record_intent_prevents_write(self):
        self.store.start_event=Mock(side_effect=OSError('disk full'))
        with self.assertRaises(OSError):self.client.request('DELETE','transactions/100')
        self.assertEqual(self.raw.writes,[])

    def test_redaction_and_paging(self):
        from sidecar.auditing import redact
        self.assertEqual(redact({'password':'s','nested':{'token':'s'}}),{'password':'[redacted]','nested':{'token':'[redacted]'}})
        for i in range(3):self.store.start_event({'action':str(i)})
        first=self.store.events(limit=2)
        self.assertEqual(len(first['events']),2)
        self.assertEqual(first['next_offset'],2)
        last=self.store.events(offset=2,limit=2)
        self.assertEqual(len(last['events']),1)
        self.assertIsNone(last['next_offset'])
