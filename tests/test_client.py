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

    def test_six_tagged_results_with_inflated_totals_stop_after_one_request(self):
        items = [{'id': str(i)} for i in range(6)]
        client = self.client([page(items)])
        self.assertEqual(client.all('tags/%23Reimburse/transactions'), items)
        client.request.assert_called_once_with('GET', 'tags/%23Reimburse/transactions', page=1, limit=100)

    def test_full_page_continues_and_short_page_stops(self):
        first = list(range(100))
        client = self.client([page(first), page([100, 101], current=2)])
        self.assertEqual(client.all('transactions', type='deposit'), first + [100, 101])
        self.assertEqual(client.request.call_count, 2)
        client.request.assert_called_with('GET', 'transactions', page=2, limit=100, type='deposit')

    def test_server_page_size_cap_does_not_truncate_results(self):
        client = self.client([page([1, 2], per_page=2), page([3], current=2, per_page=2)])
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
