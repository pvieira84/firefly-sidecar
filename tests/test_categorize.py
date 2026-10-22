import copy
import tempfile
import threading
import unittest
from sidecar.auditing import AuditedFirefly
from sidecar.store import Store
from sidecar.client import Problem
from sidecar.tools.validation import Validation
from test_reimbursements import FakeFirefly


class CategorizeFirefly(FakeFirefly):
    def all(self,path,**params):
        if path=='accounts':
            return [{'id':key,'attributes':{'name':name,'type':kind}} for key,name,kind in
                    [('1','Bank','asset'),('3','Other bank','asset'),('2','Shop','expense'),('7','Cash','cash'),('8','Income','revenue')]]
        if path in ('categories','budgets','bills'):
            return [{'id':{'categories':'10','budgets':'11','bills':'12'}[path],'attributes':{'name':path}}]
        return super().all(path,**params)


class CategorizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name+'/audit.db')
        self.raw=CategorizeFirefly();self.client=AuditedFirefly(self.raw,self.store)
        self.tool=Validation(self.client,threading.Lock())

    def tearDown(self):self.tmp.cleanup()

    def options(self,ids):return self.tool.categorize_options({'journal_ids':ids})
    def apply(self,options,jid,changes):return self.tool.categorize({'token':options['token'],'journal_id':jid,'changes':changes})

    def test_withdrawal_assignments_preserve_siblings_tags_and_amounts(self):
        before=copy.deepcopy(self.raw.groups)
        options=self.options(['12'])
        result=self.apply(options,'12',{'source_id':'3','destination_id':'7','category_id':'10','budget_id':'11','bill_id':'12'})
        self.assertTrue(result['changed'])
        row=self.raw.journal('12')[1]
        for field,value in {'source_id':'3','destination_id':'7','category_id':'10','budget_id':'11','bill_id':'12'}.items():self.assertEqual(row[field],value)
        self.assertEqual(row['amount'],'15.00');self.assertEqual(row['tags'],['Reimburse','Trip'])
        for index in (0,2):self.assertEqual(self.raw.groups['100']['attributes']['transactions'][index],before['100']['attributes']['transactions'][index])
        self.assertEqual(self.raw.writes[0][2]['group_title'],'Dinner')
        self.assertEqual(self.store.events()['events'][0]['action'],'Categorize transaction')
        self.apply(options,'12',{'category_id':'10'})
        self.assertEqual(len(self.raw.writes),1)

    def test_deposit_and_transfer_skip_withdrawal_only_assignments(self):
        for kind in ('deposit','transfer'):
            with self.subTest(kind=kind):
                row=self.raw.groups['200']['attributes']['transactions'][0]
                row.update(type=kind,source_id='1',destination_id='3',budget_id='99',bill_id='98')
                options=self.options(['21'])
                result=self.apply(options,'21',{'source_id':'8' if kind=='deposit' else '3','destination_id':'1',
                                                'category_id':'10','budget_id':'11','bill_id':None})
                self.assertEqual(result['skipped'],['budget_id','bill_id'])
                after=self.raw.journal('21')[1]
                self.assertEqual(after['budget_id'],'99');self.assertEqual(after['bill_id'],'98')

    def test_clear_assignments_and_keep_unselected_fields(self):
        row=self.raw.groups['100']['attributes']['transactions'][0]
        row.update(budget_id='11',budget_name='Budget',bill_id='12',bill_name='Bill')
        options=self.options(['11'])
        self.apply(options,'11',{'category_id':None,'budget_id':None,'bill_id':None})
        row=self.raw.journal('11')[1]
        self.assertIsNone(row['category_id']);self.assertIsNone(row['category_name'])
        self.assertIsNone(row['budget_id']);self.assertIsNone(row['bill_id'])
        self.assertEqual(row['source_id'],'1');self.assertEqual(row['destination_id'],'2')

    def test_stale_unknown_or_invalid_changes_do_not_write(self):
        options=self.options(['12'])
        for changes in ({'source_id':'2'},{'category_id':'999'},{'destination_id':None},{'amount':'99'}):
            with self.assertRaises(Problem):self.apply(options,'12',changes)
        self.raw.groups['100']['attributes']['transactions'][1]['amount']='16.00'
        with self.assertRaises(Problem):self.apply(options,'12',{'category_id':'10'})
        self.assertEqual(self.raw.writes,[])

    def test_multiple_selected_siblings_and_expired_dialog(self):
        options=self.options(['11','12'])
        self.apply(options,'11',{'category_id':'10'})
        self.apply(options,'12',{'category_id':'10'})
        self.assertEqual(self.raw.journal('11')[1]['category_id'],'10')
        self.assertEqual(self.raw.journal('12')[1]['category_id'],'10')
        options=self.options(['13']);self.tool.categorization_previews[options['token']]['created']-=601
        with self.assertRaises(Problem):self.apply(options,'13',{'category_id':'10'})

    def test_mixed_types_expose_different_account_choices(self):
        options=self.options(['12','21'])
        rows={row['journal_id']:row for row in options['transactions']}
        self.assertIn('3',rows['12']['allowed_accounts']['source_id'])
        self.assertNotIn('3',rows['21']['allowed_accounts']['source_id'])
        self.assertIn('8',rows['21']['allowed_accounts']['source_id'])
        self.assertEqual(self.raw.writes,[])
