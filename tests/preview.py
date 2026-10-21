"""Disposable development preview; uses sample data, never a real Firefly account."""
import os
import sys
import tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sidecar.server import make_handler
from sidecar.store import Store
from test_reimbursements import FakeFirefly
os.environ['SIDECAR_HOSTS'] = 'terminal.local,localhost,127.0.0.1'
with tempfile.TemporaryDirectory() as tmp:
    print('Sample-data preview at http://localhost:4173', flush=True)
    ThreadingHTTPServer(('0.0.0.0',4173),make_handler(FakeFirefly(),Store(tmp+'/preview.db'))).serve_forever()
