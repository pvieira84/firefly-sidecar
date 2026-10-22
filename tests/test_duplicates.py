import copy
import unittest
from unittest.mock import Mock
from sidecar.client import Problem
from sidecar.tools.duplicates import Duplicates


def journal(jid, amount, **kwargs):
    return dict({'transaction_journal_id':str(jid), 'amount':amount, 'type':'withdrawal',
                 'date':'2026-10-17T00:00:00+01:00', 'currency_code':'EUR',
                 'source_id':'435', 'destination_id':'7', 'source_name':'Bank',
                 'destination_name':'Merchant', 'description':'Dinner', 'tags':['todo']}, **kwargs)


def group(gid, *splits):
    return {'id':str(gid),'attributes':{'group_title':'Dinner','transactions':list(splits)}}


class DuplicateTests(unittest.TestCase):
    def run_check(self, groups, days='3'):
        client = Mock()
        client.all.return_value = groups
        result = Duplicates(client).listing('2026-10-01','2026-10-22',days)
        client.request.assert_not_called()
        client.all.assert_called_once_with('transactions',start='2026-10-01',end='2026-10-22')
        return result

    def test_split_sum_matches_unsplit_once_without_matching_own_splits(self):
        a=group(1,journal(11,'19.70'),journal(12,'0.59'),journal(13,'19.70'))
        b=group(2,journal(21,'39.99',date='2026-10-19'))
        result=self.run_check([a,b,a])
        self.assertEqual(result['scanned'],2)
        self.assertEqual(len(result['pairs']),1)
        pair=result['pairs'][0]
        self.assertEqual(pair['left']['total'],'39.99')
        self.assertEqual(len(pair['left']['splits']),3)
        self.assertEqual(pair['days_apart'],2)

    def test_decimal_sums_and_supporting_evidence(self):
        result=self.run_check([group(1,journal(1,'0.1',external_id='x'),journal(2,'0.2')),
                               group(2,journal(3,'0.3',external_id='x'))])
        self.assertEqual(result['pairs'][0]['signals'],['Same descriptions','Shared external ID'])

    def test_date_tolerance_boundary(self):
        groups=[group(1,journal(1,'10')),group(2,journal(2,'10',date='2026-10-20'))]
        self.assertEqual(len(self.run_check(groups,'3')['pairs']),1)
        self.assertEqual(len(self.run_check(groups,'2')['pairs']),0)
        self.assertEqual(len(self.run_check(groups,'0')['pairs']),0)

    def test_different_totals_currencies_types_and_accounts_do_not_match(self):
        for change in ({'amount':'11'},{'currency_code':'USD'},{'type':'deposit'},{'source_id':'99'}):
            with self.subTest(change=change):
                other=journal(2,'10');other.update(change)
                self.assertEqual(self.run_check([group(1,journal(1,'10')),group(2,other)])['pairs'],[])

    def test_deposits_use_receiving_account_and_transfers_use_both_accounts(self):
        a=journal(1,'10',type='deposit')
        b=journal(2,'10',type='deposit',source_id='99')
        self.assertEqual(len(self.run_check([group(1,a),group(2,b)])['pairs']),1)
        a['type']=b['type']='transfer'
        self.assertEqual(self.run_check([group(1,a),group(2,b)])['pairs'],[])

    def test_mixed_split_currency_account_and_dates_require_manual_review(self):
        for change in ({'currency_code':'USD'},{'source_id':'99'},{'date':'2026-10-18'}):
            with self.subTest(change=change):
                result=self.run_check([group(1,journal(1,'10'),journal(2,'10',**change))])
                self.assertEqual(len(result['skipped']),1)
                self.assertEqual(result['pairs'],[])

    def test_invalid_amounts_require_manual_review(self):
        for value in ('NaN','Infinity','-1','garbage'):
            self.assertEqual(len(self.run_check([group(1,journal(1,value))])['skipped']),1)

    def test_both_transactions_must_be_in_requested_range(self):
        result=self.run_check([group(1,journal(1,'10')),group(2,journal(2,'10',date='2026-09-30'))])
        self.assertEqual(result['pairs'],[])

    def test_invalid_filters_make_no_requests(self):
        client=Mock();tool=Duplicates(client)
        for start,end,days in (('','2026-10-22','3'),('2026-10-22','2026-10-01','3'),
                               ('2026-10-01','2026-10-22','32'),('2026-10-01','2026-10-22','1.5')):
            with self.assertRaises(Problem):tool.listing(start,end,days)
        client.all.assert_not_called()

    def test_pair_limit_is_explicit(self):
        result=self.run_check([group(i,journal(i,'10')) for i in range(34)])
        self.assertEqual(len(result['pairs']),500)
        self.assertTrue(result['truncated'])


class ReviewDuplicateTests(unittest.TestCase):
    def client(self, seeds, candidates):
        client=Mock()
        client.request.side_effect=lambda method,path:{'data':seeds[path.split('/')[1]]}
        client.all.return_value=candidates
        return client

    def test_full_split_total_matches_untagged_transaction_and_excludes_self(self):
        parent=group(1,journal(11,'19.70'),journal(12,'0.59'),journal(13,'19.70'))
        other=group(2,journal(21,'39.99',date='2026-10-20',tags=[]))
        client=self.client({'1':parent},[parent,other,other])
        result=Duplicates(client).for_review(['1'])['1']
        self.assertEqual(result['status'],'checked')
        self.assertEqual(result['source']['total'],'39.99')
        self.assertEqual(result['match_count'],1)
        self.assertEqual(result['matches'][0]['transaction']['group_id'],'2')
        client.all.assert_called_once_with('transactions',start='2026-10-14',end='2026-10-20')
        client.request.assert_called_once_with('GET','transactions/1')

    def test_overlapping_windows_are_fetched_once_and_tagged_parents_compare(self):
        parents={'1':group(1,journal(1,'10')),'2':group(2,journal(2,'10',date='2026-10-18'))}
        client=self.client(parents,[])
        result=Duplicates(client).for_review(['1','2'])
        self.assertEqual(result['1']['match_count'],1)
        self.assertEqual(result['2']['match_count'],1)
        client.all.assert_called_once_with('transactions',start='2026-10-14',end='2026-10-21')

    def test_outside_window_or_wrong_total_does_not_match(self):
        parent=group(1,journal(1,'10'))
        others=[group(2,journal(2,'10',date='2026-10-21')),group(3,journal(3,'11'))]
        result=Duplicates(self.client({'1':parent},others)).for_review(['1'])
        self.assertEqual(result['1']['match_count'],0)

    def test_empty_queue_makes_no_requests(self):
        client=Mock()
        self.assertEqual(Duplicates(client).for_review([]),{})
        client.all.assert_not_called();client.request.assert_not_called()

    def test_failure_does_not_claim_no_duplicates(self):
        parent=group(1,journal(1,'10'))
        client=self.client({'1':parent},[])
        client.all.side_effect=Problem('Firefly unavailable',502)
        self.assertEqual(Duplicates(client).for_review(['1'])['1']['status'],'unavailable')

    def test_mixed_currencies_need_manual_review(self):
        parent=group(1,journal(1,'10'),journal(2,'10',currency_code='USD'))
        client=self.client({'1':parent},[])
        self.assertEqual(Duplicates(client).for_review(['1'])['1']['status'],'manual')
        client.all.assert_not_called()

class DuplicatePagingTests(unittest.TestCase):
    def test_target_pair_after_first_500_is_retrievable_without_overlap(self):
        groups=[group(i,journal(i,'0.10',type='deposit',date='2026-09-23',destination_id='149')) for i in range(34)]
        groups += [group(22492,journal(23777,'0.55',type='deposit',date='2026-09-23',destination_id='149')),
                   group(22085,journal(23303,'0.55',type='deposit',date='2026-09-23',destination_id='149'))]
        client=Mock();client.all.return_value=groups
        checker=Duplicates(client)
        first=checker.listing('2026-09-01','2026-10-22','3')
        second=checker.listing('2026-09-01','2026-10-22','3',str(first['next_offset']))
        def pair_ids(result):
            return {tuple(sorted((p['left']['group_id'],p['right']['group_id']))) for p in result['pairs']}
        self.assertEqual(len(first['pairs']),500)
        self.assertEqual(first['next_offset'],500)
        self.assertEqual(len(second['pairs']),62)
        self.assertIsNone(second['next_offset'])
        self.assertFalse(pair_ids(first)&pair_ids(second))
        self.assertIn(('22085','22492'),pair_ids(second))
