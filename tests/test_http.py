import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from sidecar.server import make_handler
from sidecar.store import Store
from test_reimbursements import FakeFirefly


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.client=FakeFirefly()
        with patch.dict(os.environ, {'SIDECAR_PASSWORD':'','SIDECAR_HOSTS':'127.0.0.1'}):
            self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.client,Store(self.tmp.name+'/test.db')))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def req(self,path,body=None,**headers):
        request=Request(self.origin+path, data=json.dumps(body).encode() if body is not None else None,
                        headers={'Content-Type':'application/json',**headers})
        try:
            with urlopen(request) as r: return r.status, r.read(),r.headers
        except HTTPError as e: return e.code,e.read(),e.headers

    def test_saved_reimbursement_plan_for_activity_retry(self):
        store=Store(self.tmp.name+'/test.db')
        for i in range(55):
            store.save({'id':str(i),'deposit':{'group_id':'200','transaction_journal_id':'21'},'expenses':[]},'partial')
        status,body,_=self.req('/api/reimbursements/plan?plan_id=0')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['id'],'0')
        self.assertEqual(self.client.writes,[])
        status,body,_=self.req('/api/activity?action=Reimbursement&state=partial&limit=25')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['total'],55)
        self.assertEqual(self.req('/api/reimbursements/plan?plan_id=missing')[0],404)

    def test_pwa_routes_and_scopes(self):
        for base in ('', '/sidecar'):
            with patch.dict(os.environ, {'SIDECAR_BASE_PATH':base, 'SIDECAR_PASSWORD':'', 'SIDECAR_HOSTS':'127.0.0.1'}):
                self.server.RequestHandlerClass=make_handler(self.client,Store(self.tmp.name+'/pwa.db'))
            status,body,headers=self.req(base+'/manifest.webmanifest')
            self.assertEqual(status,200)
            self.assertEqual(headers['Content-Type'],'application/manifest+json')
            manifest=json.loads(body)
            self.assertEqual(manifest['start_url'],base+'/')
            self.assertEqual(manifest['scope'],base+'/')
            self.assertEqual(manifest['id'],base+'/')
            self.assertEqual(manifest['display'],'standalone')
            for icon in manifest['icons']:
                status,body,headers=self.req(icon['src'])
                self.assertEqual(status,200)
                self.assertEqual(headers['Content-Type'],'image/png')
                self.assertEqual(body[:8],b'\x89PNG\r\n\x1a\n')
                width=int.from_bytes(body[16:20],'big')
                height=int.from_bytes(body[20:24],'big')
                self.assertEqual(icon['sizes'],f'{width}x{height}')
            status,body,headers=self.req(base+'/sw.js')
            self.assertEqual(status,200)
            self.assertIn('javascript',headers['Content-Type'])
            self.assertEqual(headers['Cache-Control'],'no-store')
            self.assertEqual(self.req(base+'/offline.html')[0],200)
            self.assertEqual(self.req(base+'/pwa.js')[0],200)
            status,body,_=self.req(base+'/')
            self.assertIn(('rel="icon" type="image/png" sizes="192x192" href="'+base+'/icon-192.png"').encode(),body)
            self.assertIn((base+'/manifest.webmanifest').encode(),body)
            self.assertIn((base+'/pwa.js').encode(),body)

    def test_reverse_proxy_base_path(self):
        with patch.dict(os.environ, {'SIDECAR_BASE_PATH':'/sidecar', 'SIDECAR_PASSWORD':'', 'SIDECAR_HOSTS':'127.0.0.1'}):
            self.server.RequestHandlerClass=make_handler(self.client,Store(self.tmp.name+'/prefix.db'))
        for path in ('/', '/sidecar/', '/sidecar'):
            status,body,_=self.req(path)
            self.assertEqual(status,200)
            self.assertIn(b'data-base-path="/sidecar"',body)
            self.assertIn(b'href="/sidecar/style.css"',body)
            self.assertIn(b'src="/sidecar/app.js"',body)
            self.assertNotIn(b'__SIDECAR_BASE_PATH__',body)
        for path in ('/healthz','/sidecar/healthz','/sidecar/app.js','/sidecar/style.css'):
            self.assertEqual(self.req(path)[0],200)
        for prefix in ('', '/sidecar'):
            status,body,_=self.req(prefix+'/api/bootstrap')
            self.assertEqual(status,200)
            headers={'X-Sidecar-CSRF':json.loads(body)['csrf']}
            self.assertEqual(self.req(prefix+'/api/validation/complete',{'journal_id':'12'})[0],403)
            self.assertEqual(self.req(prefix+'/api/validation/complete',{'journal_id':'12'},**headers)[0],200)
        self.assertEqual(self.req('/sidecar-other/api/bootstrap')[0],404)

    def test_disconnected_client_does_not_trigger_second_response(self):
        from unittest.mock import Mock
        handler_type = self.server.RequestHandlerClass
        for failure in (BrokenPipeError, ConnectionResetError):
            for fail_headers in (False, True):
                handler = object.__new__(handler_type)
                handler.send_response = Mock()
                handler.send_header = Mock()
                handler.end_headers = Mock(side_effect=failure() if fail_headers else None)
                handler.wfile = Mock()
                handler.wfile.write.side_effect = failure()
                handler.respond(200, {'ok': True})
                self.assertTrue(handler.close_connection)
                handler.send_response.assert_called_once_with(200)

    def test_categorize_routes_csrf_and_audit(self):
        self.assertEqual(self.req('/api/validation/categorize-options',{'journal_ids':['12']})[0],403)
        original_all=self.client.all
        def all_options(path,**params):
            if path in ('categories','budgets','bills'):
                return [{'id':'10','attributes':{'name':'Choice'}}]
            return original_all(path,**params)
        self.client.all=all_options
        _,body,_=self.req('/api/bootstrap');headers={'X-Sidecar-CSRF':json.loads(body)['csrf']}
        status,body,_=self.req('/api/validation/categorize-options',{'journal_ids':['12']},**headers)
        self.assertEqual(status,200);token=json.loads(body)['token']
        self.assertEqual(self.client.writes,[])
        status,body,_=self.req('/api/validation/categorize',{'token':token,'journal_id':'12','changes':{'category_id':'10'}},**headers)
        self.assertEqual(status,200)
        self.assertEqual(self.client.journal('12')[1]['category_id'],'10')
        _,body,_=self.req('/api/activity')
        self.assertEqual(json.loads(body)['events'][0]['action'],'Categorize transaction')

    def test_gbit_flag_and_listing_routes(self):
        self.assertEqual(self.req('/api/validation/mark-gbit',{'journal_id':'21'})[0],403)
        _,body,_=self.req('/api/bootstrap');headers={'X-Sidecar-CSRF':json.loads(body)['csrf']}
        status,body,_=self.req('/api/validation/mark-gbit',{'journal_id':'21'},**headers)
        self.assertEqual(status,200)
        self.assertIn('#GBIT',self.client.journal('21')[1]['tags'])
        status,body,_=self.req('/api/gbit?start=2026-10-01&end=2026-10-22')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['tag'],'#GBIT')
        self.assertEqual(self.req('/api/gbit/review',{'original_id':'100','new_id':'200'})[0],403)

    def test_refund_routes_with_csrf_and_optional_todo(self):
        self.client.groups['200']['attributes']['transactions'][0].update(amount='50.00',tags=['todo','Keep'],destination_id='1')
        self.assertEqual(self.req('/api/validation/refund-candidates',{'deposit_id':'21'})[0],403)
        _,body,_=self.req('/api/bootstrap');headers={'X-Sidecar-CSRF':json.loads(body)['csrf']}
        status,body,_=self.req('/api/validation/refund-candidates',{'deposit_id':'21'},**headers)
        self.assertEqual(status,200);result=json.loads(body)
        self.assertEqual(result['candidates'][0]['total'],'50.00')
        status,body,_=self.req('/api/validation/mark-refund',{'token':result['token'],'group_id':'100','remove_todo':True},**headers)
        self.assertEqual(status,200)
        self.assertEqual(self.client.journal('21')[1]['tags'],['Keep'])
        self.assertEqual(len(self.client.linkdata),3)

    def test_mark_reimbursement_routes_and_audit(self):
        self.assertEqual(self.req('/api/validation/reimbursement-options',{'journal_id':'11'})[0],403)
        _, bootstrap, _ = self.req('/api/bootstrap')
        headers={'X-Sidecar-CSRF':json.loads(bootstrap)['csrf'], 'Origin':self.origin}
        status, raw, _ = self.req('/api/validation/reimbursement-options',{'journal_id':'11'},**headers)
        self.assertEqual(status,200)
        body={'token':json.loads(raw)['token'],'mode':'percent','value':'100'}
        self.assertEqual(self.req('/api/validation/mark-reimbursement',body)[0],403)
        self.assertEqual(self.req('/api/validation/mark-reimbursement',body,**headers)[0],200)
        _, raw, _ = self.req('/api/activity')
        self.assertIn('Mark as reimbursement',raw.decode())
        self.assertEqual(self.req('/api/validation/mark-reimbursement',body,**headers)[0],409)

    def test_complete_group_route_and_audit(self):
        self.client.groups['100']['attributes']['transactions'][0]['tags'].append('todo')
        self.client.groups['100']['attributes']['transactions'][1]['tags'].append('todo')
        self.assertEqual(self.req('/api/validation/complete-group',{'group_id':'100'})[0],403)
        _,raw,_=self.req('/api/bootstrap')
        headers={'X-Sidecar-CSRF':json.loads(raw)['csrf']}
        status,raw,_=self.req('/api/validation/complete-group',{'group_id':'100'},**headers)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['validated'],2)
        _,raw,_=self.req('/api/activity')
        self.assertEqual(json.loads(raw)['events'][0]['action'],'Validate transaction')
        self.assertEqual(json.loads(raw)['events'][0]['state'],'completed')

    def test_mark_cash_route_and_audit(self):
        self.assertEqual(self.req('/api/validation/mark-cash',{'journal_id':'12'})[0],403)
        _,body,_=self.req('/api/bootstrap');headers={'X-Sidecar-CSRF':json.loads(body)['csrf']}
        self.assertEqual(self.req('/api/validation/mark-cash',{'journal_id':'12'},**headers)[0],200)
        self.assertEqual(self.client.journal('12')[1]['destination_id'],'7')
        _,body,_=self.req('/api/activity')
        self.assertEqual(json.loads(body)['events'][0]['action'],'Mark as cash')

    def test_delete_preview_and_confirmation_require_csrf(self):
        self.assertEqual(self.req('/api/validation/delete-preview', {'group_id':'100'})[0],403)
        _,body,_=self.req('/api/bootstrap');headers={'X-Sidecar-CSRF':json.loads(body)['csrf']}
        status,body,_=self.req('/api/validation/delete-preview',{'group_id':'100'},**headers)
        self.assertEqual(status,200);token=json.loads(body)['token']
        self.assertEqual(self.client.writes,[])
        self.assertEqual(self.req('/api/validation/delete',{'token':token})[0],403)
        self.assertEqual(self.req('/api/validation/delete',{'token':token},**headers)[0],200)
        self.assertNotIn('100',self.client.groups)
        status,body,_=self.req('/api/activity')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['events'][0]['action'],'Delete transaction')
        self.assertEqual(self.req('/api/activity?offset=-1')[0],400)
        for query in ('limit=0','limit=1000','offset=abc','state=unknown','group_id=abc','start=bad','start=2026-10-23&end=2026-10-01'):
            self.assertEqual(self.req('/api/activity?'+query)[0],400)
        status,body,_=self.req('/api/activity?state=completed&group_id=100&limit=25')
        self.assertEqual(status,200)
        page=json.loads(body)
        self.assertEqual(page['limit'],25)
        self.assertIn('total',page)
        self.assertTrue(all(str(event['group_id'])=='100' and event['state']=='completed' for event in page['events']))

    def test_duplicate_checker_is_read_only_and_validates_filters(self):
        import copy
        other=copy.deepcopy(self.client.groups['200'])
        other['id']='201'
        other['attributes']['transactions'][0]['transaction_journal_id']='22'
        self.client.all=lambda path, **params:[self.client.groups['200'],other]
        status,body,_=self.req('/api/duplicates?start=2026-10-01&end=2026-10-22&days=3')
        self.assertEqual(status,200)
        self.assertEqual(len(json.loads(body)['pairs']),1)
        self.assertEqual(self.client.writes,[])
        self.assertEqual(self.req('/api/duplicates?start=bad&end=2026-10-22')[0],400)

    def test_validation_http_journey_and_csrf(self):
        self.client.groups['100']['attributes']['transactions'][0]['tags'] = ['todo', 'Personal']
        status, body, _ = self.req('/api/validation')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['transactions'][0]['journal_id'], '11')
        self.assertEqual(self.req('/api/validation/complete', {'journal_id':'11'})[0], 403)
        _, body, _ = self.req('/api/bootstrap')
        token = json.loads(body)['csrf']
        status, body, _ = self.req('/api/validation/complete', {'journal_id':'11'}, **{'X-Sidecar-CSRF':token})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['complete'])
        self.assertEqual(self.client.journal('11')[1]['tags'], ['Personal'])

    def test_http_journey(self):
        status,body,headers=self.req('/')
        self.assertEqual(status,200)
        self.assertIn(b'Reimbursements',body)
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        _,body,_=self.req('/api/bootstrap');config=json.loads(body)
        self.assertNotIn('server-secret',body.decode())
        status,body,_=self.req('/api/reimbursements');self.assertEqual(status,200)
        self.assertEqual(len(json.loads(body)['expenses']),2)
        status,body,_=self.req('/api/reimbursements/review',{'deposit_id':'21','expense_ids':['12','13']},**{'X-Sidecar-CSRF':config['csrf']})
        self.assertEqual(status,200);plan=json.loads(body)
        status,body,_=self.req('/api/reimbursements/apply',{'plan_id':plan['id']},**{'X-Sidecar-CSRF':config['csrf']})
        self.assertEqual(status,200);self.assertTrue(json.loads(body)['complete'])
        status,body,_=self.req('/api/history');self.assertEqual(json.loads(body)[0]['state'],'complete')

    def test_csrf_and_unknown_host_rejected(self):
        self.assertEqual(self.req('/api/reimbursements/review',{'deposit_id':'21','expense_ids':['12']})[0],403)
        self.assertEqual(self.req('/api/bootstrap',Host='attacker.test')[0],403)
        self.assertEqual(self.client.writes,[])

    def test_bad_dates_and_static_traversal(self):
        self.assertEqual(self.req('/api/reimbursements?start=invalid')[0],400)
        self.assertEqual(self.req('/../server.py')[0],404)


if __name__=='__main__': unittest.main()
