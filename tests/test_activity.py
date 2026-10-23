import tempfile
import unittest
from sidecar.store import Store


class ActivityTests(unittest.TestCase):
    def test_filtered_pagination_counts_boundaries_and_action_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp+'/activity.db')
            with store.db() as db:
                import json
                for i in range(80):
                    day='22' if i<70 else '23'
                    payload={'action':'Delete transaction' if i%2==0 else 'Update transaction tags',
                             'group_id':'100' if i%2==0 else '200'}
                    db.execute('INSERT INTO events VALUES (?,?,?,?,?)',
                               (str(i),'2026-10-'+day+f'T12:00:{i%60:02d}+00:00','now',
                                'completed' if i%2==0 else 'uncertain',json.dumps(payload)))
            filters=dict(state='completed',action='Delete transaction',group_id='100',start='2026-10-22',end='2026-10-22')
            first=store.events(limit=25,**filters)
            self.assertEqual(first['total'],35)
            self.assertEqual(len(first['events']),25)
            self.assertEqual(first['next_offset'],25)
            self.assertIsNone(first['previous_offset'])
            second=store.events(offset=25,limit=25,**filters)
            self.assertEqual(len(second['events']),10)
            self.assertIsNone(second['next_offset'])
            self.assertEqual(second['previous_offset'],0)
            self.assertFalse({e['id'] for e in first['events']}&{e['id'] for e in second['events']})
            self.assertEqual(store.events(offset=1000,limit=25,**filters)['offset'],25)
            self.assertEqual(store.events(group_id="100' OR 1=1 --")['total'],0)
            self.assertEqual(store.events(state='blocked')['total'],0)
            self.assertEqual(first['actions'],['Delete transaction','Update transaction tags'])
            self.assertEqual(store.events(start='2026-10-23',end='2026-10-23')['total'],10)
