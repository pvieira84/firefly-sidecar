import copy
import unittest
from unittest.mock import Mock
from sidecar.client import Firefly, Problem
from sidecar.tools.duplicates import Duplicates
from test_reimbursements import FakeFirefly


class NativeAmountsTests(unittest.TestCase):
    def test_primary_currency_is_read_from_firefly_and_cached(self):
        client=object.__new__(Firefly)
        client.request=Mock(return_value={'data':{'attributes':{'code':'GBP','symbol':'£','decimal_places':2}}})
        self.assertEqual(client.primary_currency()['code'],'GBP')
        self.assertEqual(client.primary_currency()['code'],'GBP')
        client.request.assert_called_once_with('GET','currencies/primary')

    def test_older_firefly_default_endpoint(self):
        client=object.__new__(Firefly)
        client.request=Mock(side_effect=[Problem('Not supported',502),{'data':{'attributes':{'code':'EUR'}}}])
        self.assertEqual(client.primary_currency()['code'],'EUR')
        self.assertEqual(client.request.call_args.args,('GET','currencies/default'))

    def test_normalized_splits_keep_recorded_currency_amounts(self):
        group=copy.deepcopy(FakeFirefly().groups['100'])
        values={'pc_amount':'1803.12','native_amount':'1803.12','primary_currency_code':'EUR',
                'foreign_amount':'1785.00','foreign_currency_code':'EUR'}
        for split in group['attributes']['transactions']:
            split.update(values,currency_code='USD')
        row,reason=Duplicates.summarize('100',group)
        self.assertIsNone(reason)
        for split in row['splits']:
            for key,value in values.items():self.assertEqual(split[key],value)
