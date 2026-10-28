import threading
import time
import unittest
from unittest.mock import patch
from sidecar.client import Problem
import test_amazon as fixtures
order=fixtures.order

class AmazonProgressTests(unittest.TestCase):
    setUp=fixtures.AmazonTests.setUp
    tearDown=fixtures.AmazonTests.tearDown

    def test_matching_reports_loading_and_each_distinct_order(self):
        self.tool.ingest({'orders':[order(),dict(order(),orderId='123-1234567-1234568')]})
        updates=[]
        result=self.tool.listing('2026-10-01','2026-10-31',progress=updates.append)
        self.assertEqual([p['phase'] for p in updates[:2]],['loading','loading'])
        self.assertEqual([(p['checked'],p['total']) for p in updates if p['phase']=='matching'],[(0,2),(1,2),(2,2)])
        self.assertEqual((result['stored'],result['not_enriched']),(2,2))
        self.assertEqual(self.fake.writes,[])

    def test_match_result_identifies_its_revision_without_hiding_new_imports(self):
        self.tool.ingest({'orders':[order()]})
        before=self.tool.status()['revision']
        changed=False
        def progress(update):
            nonlocal changed
            if not changed:
                changed=True
                self.tool.ingest({'orders':[dict(order(),orderId='123-1234567-1234568')]})
        result=self.tool.listing('2026-10-01','2026-10-31',progress=progress)
        self.assertEqual(result['revision'],before)
        self.assertNotEqual(result['revision'],self.tool.status()['revision'])

    def test_global_counts_do_not_depend_on_match_range(self):
        self.tool.ingest({'orders':[order(),dict(order(),orderId='123-1234567-1234568')]})
        listing=self.tool.listing('2026-10-01','2026-10-31')
        entry=next(e for e in listing['orders'] if e['candidates'])
        plan=self.tool.review({'key':entry['key'],'journal_id':entry['candidates'][0]['journal_id'],'start':'2026-10-01','end':'2026-10-31'})
        self.tool.apply({'plan_id':plan['id']})
        self.assertEqual(self.tool.status()['not_enriched'],1)
        self.assertEqual(self.tool.listing('2020-01-01','2020-01-02')['not_enriched'],1)
        self.tool.ingest({'orders':[dict(order(),items=[{'title':'Changed','quantity':1}])]})
        self.assertEqual(self.tool.status()['not_enriched'],2)

    def test_job_progress_busy_guard_completion_and_failure(self):
        entered=threading.Event();release=threading.Event()
        def listing(**kw):
            kw['progress']({'phase':'matching','checked':1,'total':2,'message':'Checking'})
            entered.set();release.wait(2)
            return {'orders':[],'stored':2,'not_enriched':1}
        with patch.object(self.tool,'listing',side_effect=listing):
            jid=self.tool.start_matches({'start':'2026-10-01','end':'2026-10-31'})['id']
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.tool.match_status(jid)['checked'],1)
            with self.assertRaises(Problem):self.tool.start_matches({})
            release.set()
            deadline=time.monotonic()+2
            while self.tool.match_status(jid)['state']=='running' and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(self.tool.match_status(jid)['result']['not_enriched'],1)
        with patch.object(self.tool,'listing',side_effect=Problem('Failed lookup',502)):
            jid=self.tool.start_matches({})['id']
            deadline=time.monotonic()+2
            while self.tool.match_status(jid)['state']=='running' and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(self.tool.match_status(jid)['error'],'Failed lookup')
        with self.assertRaises(Problem):self.tool.match_status('unknown')
        self.assertEqual(self.fake.writes,[])
