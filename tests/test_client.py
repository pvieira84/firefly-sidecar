import unittest
from unittest.mock import Mock
from sidecar.client import Firefly


def page(items, current=1, total_pages=22, per_page=100):
    return {'data': items, 'meta': {'pagination': {
        'total': 2163, 'count': len(items), 'per_page': per_page,
        'current_page': current, 'total_pages': total_pages}}}


class PaginationTests(unittest.TestCase):
    def client(self, responses):
        client = object.__new__(Firefly)
        client.request = Mock(side_effect=responses)
        return client

    def test_six_tagged_results_with_inflated_totals_stop_at_first_empty_page(self):
        items = [{'id': str(i)} for i in range(6)]
        client = self.client([page(items),page([],current=2)])
        self.assertEqual(client.all('tags/%23Reimburse/transactions'), items)
        self.assertEqual(client.request.call_count,2)
        client.request.assert_called_with('GET', 'tags/%23Reimburse/transactions', page=2, limit=100)

    def test_full_page_continues_and_reported_last_page_stops(self):
        first = list(range(100))
        client = self.client([page(first), page([100, 101], current=2,total_pages=2)])
        self.assertEqual(client.all('transactions', type='deposit'), first + [100, 101])
        self.assertEqual(client.request.call_count, 2)
        client.request.assert_called_with('GET', 'transactions', page=2, limit=100, type='deposit')

    def test_server_page_size_cap_does_not_truncate_results(self):
        client = self.client([page([1, 2], per_page=2), page([3], current=2, per_page=2,total_pages=2)])
        self.assertEqual(client.all('transactions'), [1, 2, 3])
        self.assertEqual(client.request.call_count, 2)

    def test_empty_page_stops_despite_inflated_total(self):
        client = self.client([page([])])
        self.assertEqual(client.all('transactions'), [])
        self.assertEqual(client.request.call_count, 1)

    def test_last_full_page_stops_at_reported_end(self):
        client = self.client([page([1, 2], total_pages=1, per_page=2)])
        self.assertEqual(client.all('transactions'), [1, 2])
        self.assertEqual(client.request.call_count, 1)


class ValidationErrorTests(unittest.TestCase):
    def test_validation_details_are_reported_without_token_or_trace(self):
        import io
        import json
        from urllib.error import HTTPError
        from sidecar.client import Problem
        client = object.__new__(Firefly)
        client.url = 'http://firefly.test'
        client.token = 'private-token'
        client.opener = Mock()
        payload = {'errors': {'transactions.0.description': ['Description is required. private-token']},
                   'trace': 'internal stack trace'}
        client.opener.open.side_effect = HTTPError('http://firefly.test', 422, 'Invalid', {},
                                                   io.BytesIO(json.dumps(payload).encode()))
        with self.assertRaises(Problem) as caught:
            client.request('PUT', 'transactions/22454', {})
        self.assertIn('transactions.0.description: Description is required.', str(caught.exception))
        self.assertNotIn('private-token', str(caught.exception))
        self.assertNotIn('internal stack trace', str(caught.exception))

    def test_non_json_validation_response_has_safe_fallback(self):
        import io
        from urllib.error import HTTPError
        from sidecar.client import Problem
        client = object.__new__(Firefly)
        client.url = 'http://firefly.test'
        client.token = 'private-token'
        client.opener = Mock()
        client.opener.open.side_effect = HTTPError('http://firefly.test', 422, 'Invalid', {},
                                                   io.BytesIO(b'<html>private-token</html>'))
        with self.assertRaises(Problem) as caught:
            client.request('PUT', 'transactions/22454', {})
        self.assertIn('No structured validation details', str(caught.exception))
        self.assertNotIn('<html>', str(caught.exception))


class DeleteResponseTests(unittest.TestCase):
    def test_successful_delete_with_no_content(self):
        client=object.__new__(Firefly)
        client.url='http://firefly.test';client.token='secret'
        from unittest.mock import MagicMock
        client.opener=MagicMock()
        response=client.opener.open.return_value.__enter__.return_value
        response.status=204
        self.assertEqual(client.request('DELETE','transactions/100'),{})
        response.read.assert_not_called()


class ShortParentPageTests(unittest.TestCase):
    def test_short_nonempty_pages_do_not_hide_duplicate_deposits(self):
        from sidecar.tools.duplicates import Duplicates
        from test_duplicates import group, journal
        first=[group(i,journal(i,str(i+10))) for i in range(97)]
        first.append(group(22492,journal(23777,'0.55',type='deposit',date='2026-09-23',destination_id='149')))
        second=[group(22085,journal(23303,'0.55',type='deposit',date='2026-09-23',destination_id='149'))]
        client=object.__new__(Firefly)
        client.request=Mock(side_effect=[page(first,total_pages=2),page(second,current=2,total_pages=2)])
        result=Duplicates(client).listing('2026-09-01','2026-10-22','3')
        pairs={frozenset((p['left']['group_id'],p['right']['group_id'])) for p in result['pairs']}
        self.assertIn(frozenset(('22492','22085')),pairs)
        self.assertEqual(result['scanned'],99)
        self.assertEqual(client.request.call_count,2)

    def test_nonempty_short_middle_page_does_not_stop_next_page(self):
        client=object.__new__(Firefly)
        client.request=Mock(side_effect=[page([1],total_pages=3),page([2],current=2,total_pages=3),page([3],current=3,total_pages=3)])
        self.assertEqual(client.all('transactions'),[1,2,3])
