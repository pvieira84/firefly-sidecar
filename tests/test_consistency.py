import copy
import os
import threading
import unittest
from unittest.mock import patch
from sidecar.client import Problem
from sidecar.tools.consistency import Consistency
from sidecar.tools.validation import Validation
from test_reimbursements import FakeFirefly


class ScanFirefly(FakeFirefly):
    def __init__(self):
        super().__init__();self.reads=[];self.links={};self.more=False

    def request(self,method,path,body=None,**params):
        if method!='GET':raise AssertionError('Consistency checking must not write')
        self.reads.append((path,params))
        if path=='transactions' or (path.startswith(('accounts/','tags/')) and path.endswith('/transactions')):
            return {'data':copy.deepcopy(list(self.groups.values())), 'meta':{'pagination':{'total_pages':2 if self.more else 1}}}
        if path.startswith('transaction-journals/') and path.endswith('/links'):
            value=self.links.get(path.split('/')[1],[])
            if isinstance(value,Exception):raise value
            return {'data':[{'id':str(i),'attributes':link} for i,link in enumerate(value)]}
        return super().request(method,path,body,**params)


class ConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.raw=ScanFirefly();self.validation=Validation(self.raw,threading.RLock());self.tool=Consistency(self.raw,self.validation)
        self.filters={'start':'2026-10-01','end':'2026-10-31','limit':'25'}

    def scan(self,**filters):return self.tool.scan(dict(self.filters,**filters))
    def link(self,kind,inward,outward):
        value={'link_type_name':kind,'inward_id':inward,'outward_id':outward}
        for jid in (inward,outward):self.raw.links.setdefault(jid,[]).append(value)

    def test_tagged_reimbursements_and_cash_fields_are_checked_per_split(self):
        result=self.scan(rule='reimbursement')
        self.assertEqual({row['journal_id'] for row in result['findings']},{'12','13'})
        row=self.raw.groups['100']['attributes']['transactions'][1]
        row.update(destination_id='7',category_id='9',category_name='Dining',budget_id='8',bill_id='6')
        issues=next(row['issues'] for row in self.scan(rule='reimbursement')['findings'] if row['journal_id']=='12')
        self.assertEqual(issues,['Category must be cleared','Budget must be cleared','Subscription must be cleared'])

    def test_refund_checks_both_journals_without_touching_siblings(self):
        self.link('Refund','21','11')
        result=self.scan(rule='refund')
        self.assertEqual({row['journal_id'] for row in result['findings']},{'11','21'})
        self.assertEqual(result['checked'],4)
        self.assertTrue(all(method!='PUT' for method,_ in self.raw.reads))
        self.assertEqual(self.raw.writes,[])

    def test_gbit_only_checks_replacement_and_refund_not_original(self):
        self.raw.groups['300']=copy.deepcopy(self.raw.groups['100'])
        self.raw.groups['300']['id']='300'
        self.raw.groups['300']['attributes']['transactions']=[copy.deepcopy(self.raw.groups['100']['attributes']['transactions'][0])]
        self.raw.groups['300']['attributes']['transactions'][0]['transaction_journal_id']='31'
        self.link('GBIT','11','31');self.link('GBIT Refund','21','11')
        result=self.scan(rule='gbit')
        self.assertEqual({row['journal_id'] for row in result['findings']},{'21','31'})

    def test_configured_names_and_transfer_cash_settings(self):
        with patch.dict(os.environ,{'GBIT_LINK_TYPE':'GBIT From','REIMBURSE_TAG':'Claim'}):
            row=self.raw.groups['100']['attributes']['transactions'][1]
            row.update(type='transfer',tags=['Claim'],source_id='1',destination_id='2',budget_id=None,bill_id=None)
            result=self.scan(rule='reimbursement')
            self.assertEqual(result['applicable'],1)
            self.assertEqual(result['findings'],[])

    def test_filters_bound_collection_and_do_not_follow_next_page(self):
        self.raw.more=True
        result=self.scan(account_id='1',tag='Reimburse',type='withdrawal')
        path,params=self.raw.reads[0]
        self.assertEqual(path,'accounts/1/transactions')
        self.assertEqual(params,{'start':'2026-10-01','end':'2026-10-31','page':1,'limit':25,'type':'withdrawal'})
        self.assertEqual(result['checked'],2)
        self.assertEqual(result['next_page'],2)
        self.assertEqual(sum(path=='accounts/1/transactions' for path,_ in self.raw.reads),1)
        result=self.scan(group_id='100',rule='refund')
        self.assertEqual(result['next_page'],None)

    def test_invalid_filters_make_no_requests(self):
        for changes in ({'start':''},{'end':'2025-01-01'},{'limit':'1000'},{'page':'0'},{'account_id':'bad'},{'group_id':'bad'},{'rule':'bad'}):
            with self.assertRaises(Problem):self.scan(**changes)
        self.assertEqual(self.raw.reads,[])

    def test_link_failure_is_incomplete_not_clean(self):
        self.raw.links['11']=Problem('Firefly unavailable',502)
        result=self.scan(rule='refund')
        self.assertEqual(result['errors'][0]['journal_id'],'11')
        self.assertEqual(self.raw.writes,[])

    def test_links_with_more_pages_are_marked_incomplete(self):
        original=self.raw.request
        def request(method,path,body=None,**params):
            result=original(method,path,body,**params)
            if path=='transaction-journals/11/links':result['meta']={'pagination':{'total_pages':2}}
            return result
        self.raw.request=request
        self.assertEqual(self.scan(rule='refund')['errors'][0]['journal_id'],'11')

    def test_oversized_parent_stops_before_link_lookups(self):
        base=self.raw.groups['100']['attributes']['transactions'][0]
        self.raw.groups['100']['attributes']['transactions']=[dict(base,transaction_journal_id=str(i+1000)) for i in range(501)]
        with self.assertRaises(Problem):self.scan()
        self.assertFalse(any(path.endswith('/links') for path,_ in self.raw.reads))

    def test_gbit_label_aliases_and_id_only_links(self):
        self.raw.groups['300']=copy.deepcopy(self.raw.groups['100'])
        self.raw.groups['300']['id']='300'
        self.raw.groups['300']['attributes']['transactions']=[dict(self.raw.groups['100']['attributes']['transactions'][0],transaction_journal_id='31')]
        self.link('GBIT From','11','31');self.link('GBIT Refunds','21','11')
        self.assertEqual({row['journal_id'] for row in self.scan(rule='gbit')['findings']},{'31','21'})
        self.raw.links={}
        self.raw.links['11']=[{'link_type_id':'5','inward_id':'21','outward_id':'11'}]
        self.assertEqual(self.scan(rule='refund')['findings'][0]['journal_id'],'11')

    def test_long_date_ranges_and_all_evaluated_statuses(self):
        result=self.scan(start='2000-01-01',end='2030-12-31',rule='reimbursement')
        self.assertEqual(len(result['evaluated']),4)
        self.assertEqual(len(result['findings']),2)
        self.assertEqual({row['status'] for row in result['evaluated']},{'not_applicable','inconsistent'})
        for row in self.raw.groups['100']['attributes']['transactions'][1:]:row['destination_id']='7'
        result=self.scan(rule='reimbursement')
        self.assertEqual({row['status'] for row in result['evaluated']},{'not_applicable','consistent'})
        self.raw.links['11']=Problem('Unavailable',502)
        result=self.scan(rule='refund')
        self.assertEqual(next(row for row in result['evaluated'] if row['journal_id']=='11')['status'],'incomplete')

    def test_full_scan_covers_later_pages_and_reports_progress(self):
        original=self.raw.request;updates=[]
        def request(method,path,body=None,**params):
            if path=='transactions':
                group=copy.deepcopy(self.raw.groups['100' if params['page']==1 else '200'])
                return {'data':[group],'meta':{'pagination':{'total_pages':2}}}
            return original(method,path,body,**params)
        self.raw.request=request
        self.link('Refund','21','11')
        result=self.tool.scan(self.filters,full=True,progress=lambda **data:updates.append(data))
        self.assertEqual(result['checked'],4)
        self.assertEqual(result['groups'],2)
        self.assertIn('21',[row['journal_id'] for row in result['findings']])
        self.assertIsNone(result['next_page'])
        self.assertEqual([update['pages'] for update in updates if update['phase']=='collecting'],[1,2])
        self.assertEqual(updates[-1]['checked'],4)

    def test_job_results_paginate_without_rescanning(self):
        import time
        job_id=self.tool.start(self.filters)['id']
        for _ in range(200):
            status=self.tool.status(job_id)
            if status['state']!='running':break
            time.sleep(.005)
        self.assertEqual(status['state'],'complete')
        reads=len(self.raw.reads)
        first=self.tool.results(job_id,limit='25',show='all')
        self.assertEqual(first['total'],4)
        filtered=self.tool.results(job_id,limit='50',show='inconsistent')
        self.assertEqual(filtered['total'],2)
        self.assertEqual(len(self.raw.reads),reads)
        self.assertNotIn('result',status)

    def test_job_cancellation_stops_full_scan(self):
        import time
        entered=threading.Event();release=threading.Event();original=self.raw.request
        def paused(method,path,body=None,**params):
            if path=='transactions':entered.set();release.wait(2)
            return original(method,path,body,**params)
        self.raw.request=paused
        job_id=self.tool.start(self.filters)['id']
        self.assertTrue(entered.wait(1))
        self.tool.cancel(job_id);release.set()
        for _ in range(200):
            status=self.tool.status(job_id)
            if status['state']!='running':break
            time.sleep(.005)
        self.assertEqual(status['state'],'cancelled')
        self.assertFalse(any(path.endswith('/links') for path,_ in self.raw.reads))
        with self.assertRaises(Problem):self.tool.results(job_id)

    def test_full_scan_follows_all_link_pages(self):
        original=self.raw.request
        def request(method,path,body=None,**params):
            if path=='transaction-journals/11/links':
                links=[{'id':'1','attributes':{'link_type_name':'Unrelated','inward_id':'11','outward_id':'99'}}] if params['page']==1 else [{'id':'2','attributes':{'link_type_name':'Refund','inward_id':'21','outward_id':'11'}}]
                return {'data':links,'meta':{'pagination':{'total_pages':2}}}
            return original(method,path,body,**params)
        self.raw.request=request
        result=self.tool.scan(dict(self.filters,rule='refund'),full=True)
        self.assertIn('11',[row['journal_id'] for row in result['findings']])
        self.assertEqual(result['errors'],[])


class RepairFirefly(ScanFirefly):
    def request(self,method,path,body=None,**params):
        if method=='GET':return super().request(method,path,body,**params)
        return FakeFirefly.request(self,method,path,body,**params)


class ConsistencyFixTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from sidecar.store import Store
        from sidecar.auditing import AuditedFirefly
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name+'/activity.db')
        self.raw=RepairFirefly();self.client=AuditedFirefly(self.raw,self.store)
        self.validation=Validation(self.client,threading.RLock());self.tool=Consistency(self.client,self.validation)
        result=self.tool.scan({'start':'2026-10-01','end':'2026-10-31','rule':'reimbursement'},full=True)
        self.tool.jobs['job']={'state':'complete','result':result,'filters':{'rule':'reimbursement'}}

    def tearDown(self):self.tmp.cleanup()

    def preview(self):return self.tool.fix_preview({'id':'job','journal_id':'12'})

    def test_fix_is_audited_preserves_siblings_tags_amounts_and_updates_report(self):
        before=copy.deepcopy(self.raw.groups['100'])
        preview=self.preview()
        self.assertEqual(preview['changes']['destination_id'],'7')
        self.assertEqual(self.raw.writes,[])
        self.assertTrue(self.tool.fix({'token':preview['token']})['complete'])
        rows=self.raw.groups['100']['attributes']['transactions']
        self.assertEqual(rows[0],before['attributes']['transactions'][0])
        self.assertEqual(rows[2],before['attributes']['transactions'][2])
        for field in ('tags','amount','description','source_id'):
            self.assertEqual(rows[1][field],before['attributes']['transactions'][1][field])
        self.assertEqual(rows[1]['destination_id'],'7')
        self.assertEqual(self.tool.results('job')['total'],1)
        events=self.store.events()['events']
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['action'],'Mark as cash')
        self.assertEqual(events[0]['state'],'completed')
        with self.assertRaises(Problem):self.tool.fix({'token':preview['token']})
        self.assertEqual(len(self.raw.writes),1)

    def test_stale_preview_blocks_write(self):
        preview=self.preview()
        self.raw.groups['100']['attributes']['transactions'][0]['description']='Changed sibling'
        with self.assertRaises(Problem):self.tool.fix({'token':preview['token']})
        self.assertEqual(self.raw.writes,[])

    def test_stale_scan_and_expired_tokens_are_rejected(self):
        self.raw.groups['100']['attributes']['transactions'][1]['amount']='99'
        with self.assertRaises(Problem):self.preview()
        self.raw.groups['100']['attributes']['transactions'][1]['amount']='15.00'
        preview=self.preview();self.tool.fixes[preview['token']]['created']-=601
        with self.assertRaises(Problem):self.tool.fix({'token':preview['token']})
        self.assertEqual(self.raw.writes,[])

    def test_incomplete_check_is_not_fixable(self):
        self.tool.jobs['job']['result']['evaluated'][1]['check_errors']=['Lookup failed']
        with self.assertRaises(Problem):self.preview()
        self.assertEqual(self.raw.writes,[])

    def test_removed_rule_link_blocks_fix(self):
        self.raw.links['11']=[{'link_type_name':'Refund','inward_id':'21','outward_id':'11'}]
        result=self.tool.scan({'start':'2026-10-01','end':'2026-10-31','rule':'refund'},full=True)
        self.tool.jobs['job'].update(result=result,filters={'rule':'refund'})
        preview=self.tool.fix_preview({'id':'job','journal_id':'11'})
        self.raw.links['11']=[]
        with self.assertRaises(Problem):self.tool.fix({'token':preview['token']})
        self.assertEqual(self.raw.writes,[])
