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
