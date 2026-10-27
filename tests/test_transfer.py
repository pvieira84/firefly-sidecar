import copy
import threading
import unittest
from sidecar.client import Problem
from sidecar.tools.validation import Validation
from test_reimbursements import FakeFirefly

class TransferTests(unittest.TestCase):
    def setUp(self):
        self.client=FakeFirefly()
        self.original=self.client.request
        self.accounts={'1':{'type':'asset','name':'Bank'},'3':{'type':'asset','name':'Savings'},'4':{'type':'expense','name':'Shop'}}
        original_all=self.client.all
        self.client.all=lambda path,**kw: [{'id':key,'attributes':value} for key,value in self.accounts.items()] if path=='accounts' else original_all(path,**kw)
        def request(method,path,body=None,**params):
            if method=='GET' and path.startswith('accounts/'):
                return {'data':{'attributes':self.accounts[path.split('/')[1]]}}
            return self.original(method,path,body,**params)
        self.client.request=request
        self.tool=Validation(self.client,threading.Lock())

    def preview(self,jid='11'):
        return self.tool.transfer_options({'journal_id':jid})

    def apply(self,p,source='1',destination='3'):
        return self.tool.convert_transfer({'token':p['token'],'source_id':source,'destination_id':destination})

    def test_whole_split_group_and_deposit_preserve_details(self):
        for gid,jid in [('100','11'),('200','21')]:
            before=copy.deepcopy(self.client.groups[gid])
            p=self.preview(jid)
            self.assertEqual({a['id'] for a in p['accounts']},{'1','3'})
            self.assertEqual(self.apply(p)['converted'],len(before['attributes']['transactions']))
            for row in before['attributes']['transactions']:
                row.update(type='transfer',source_id='1',destination_id='3',budget_id=None,budget_name=None,bill_id=None,bill_name=None)
            self.assertEqual(self.client.groups[gid],before)
            with self.assertRaises(Problem):self.apply(p)
        self.assertFalse(self.client.writes[0][2]['apply_rules'])
        self.assertFalse(self.client.writes[0][2]['fire_webhooks'])
        with self.assertRaises(Problem):self.preview()

    def test_stale_sibling_same_accounts_and_invalid_accounts_no_write(self):
        p=self.preview()
        for source,destination in [('1','1'),('1','4')]:
            with self.assertRaises(Problem):self.apply(p,source,destination)
        self.accounts['3']['active']=False
        with self.assertRaises(Problem):self.apply(p)
        self.accounts['3']['active']=True
        self.client.groups['100']['attributes']['transactions'][1]['description']='Edited sibling'
        with self.assertRaises(Problem):self.apply(p)
        self.assertEqual(self.client.writes,[])

    def test_expired_and_uncertain_write_cannot_replay(self):
        p=self.preview();self.tool.transfer_previews[p['token']]['created']-=601
        with self.assertRaises(Problem):self.apply(p)
        p=self.preview()
        # Preserve account reader while simulating a lost PUT response.
        reader=self.client.request
        def request(method,path,body=None,**kw):
            result=reader(method,path,body,**kw)
            if method=='PUT':raise Problem('Lost response',502)
            return result
        self.client.request=request
        with self.assertRaises(Problem):self.apply(p)
        with self.assertRaises(Problem):self.apply(p)
        self.assertEqual(len(self.client.writes),1)

    def test_verification_detects_changed_amount(self):
        p=self.preview();original=self.client.request
        def changed(method,path,body=None,**kw):
            result=original(method,path,body,**kw)
            if method=='PUT':self.client.groups['100']['attributes']['transactions'][0]['amount']='999'
            return result
        self.client.request=changed
        with self.assertRaises(Problem):self.apply(p)
