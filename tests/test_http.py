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

    def test_refund_routes_with_csrf_and_optional_todo(self):
        self.client.groups['200']['attributes']['transactions'][0].update(amount='50.00',tags=['todo','Keep'])
        self.assertEqual(self.req('/api/validation/refund-candidates',{'deposit_id':'21'})[0],403)
        _,body,_=self.req('/api/bootstrap');headers={'X-Sidecar-CSRF':json.loads(body)['csrf']}
        status,body,_=self.req('/api/validation/refund-candidates',{'deposit_id':'21'},**headers)
        self.assertEqual(status,200);result=json.loads(body)
        self.assertEqual(result['candidates'][0]['total'],'50.00')
        status,body,_=self.req('/api/validation/mark-refund',{'token':result['token'],'group_id':'100','remove_todo':True},**headers)
        self.assertEqual(status,200)
        self.assertEqual(self.client.journal('21')[1]['tags'],['Keep'])
        self.assertEqual(len(self.client.linkdata),3)

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
