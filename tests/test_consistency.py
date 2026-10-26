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
        for changes in ({'start':''},{'end':'2028-01-01'},{'limit':'1000'},{'page':'0'},{'account_id':'bad'},{'group_id':'bad'},{'rule':'bad'}):
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
