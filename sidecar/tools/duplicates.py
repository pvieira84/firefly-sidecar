from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from ..client import Problem


class Duplicates:
    """Read-only comparison of parent transaction totals, never individual split pairs."""
    def __init__(self, client):
        self.client = client

    def listing(self, start, end, tolerance='3'):
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
            days = int(tolerance)
        except (ValueError, TypeError):
            raise Problem('Choose valid start/end dates and a whole-number date tolerance.') from None
        if first > last or not 0 <= days <= 31:
            raise Problem('Start must be on or before end; date tolerance must be between 0 and 31 days.')
        groups = {str(g['id']): g for g in self.client.all('transactions', start=start, end=end)}
        buckets, skipped = defaultdict(list), []
        for gid, group in groups.items():
            row, reason = self.summarize(gid, group)
            if reason:
                skipped.append({'group_id': gid, 'title': group['attributes'].get('group_title') or gid, 'reason': reason})
                continue
            if not first <= date.fromisoformat(row['date']) <= last:
                continue
            key = (row['type'], row['currency'], row['account_key'], Decimal(row['total']))
            buckets[key].append(row)
        pairs = []
        for rows in buckets.values():
            rows.sort(key=lambda r: (r['date'], r['group_id']))
            for index, right in enumerate(rows):
                for previous in range(index - 1, -1, -1):
                    left = rows[previous]
                    gap = (date.fromisoformat(right['date']) - date.fromisoformat(left['date'])).days
                    if gap > days:
                        break
                    if len(pairs) >= 500:
                        return {'pairs': pairs, 'skipped': skipped, 'scanned': len(groups), 'truncated': True}
                    signals = []
                    if left['descriptions'] and left['descriptions'] == right['descriptions']:
                        signals.append('Same descriptions')
                    if set(left['external_ids']) & set(right['external_ids']):
                        signals.append('Shared external ID')
                    pairs.append({'left': left, 'right': right, 'days_apart': gap, 'signals': signals})
        return {'pairs': pairs, 'skipped': skipped, 'scanned': len(groups), 'truncated': False}

    @staticmethod
    def summarize(gid, group):
        splits = group['attributes'].get('transactions') or []
        if not splits:
            return None, 'No journals returned.'
        kinds = {s.get('type') for s in splits}
        currencies = {s.get('currency_code') for s in splits}
        dates = {str(s.get('date') or '')[:10] for s in splits}
        if len(kinds) != 1 or next(iter(kinds)) not in ('withdrawal', 'deposit', 'transfer'):
            return None, 'Mixed or unsupported transaction types.'
        kind = next(iter(kinds))
        if len(currencies) != 1 or not next(iter(currencies)):
            return None, 'Mixed or missing currencies; totals require manual review.'
        if len(dates) != 1:
            return None, 'Split dates differ; requires manual review.'
        try:
            transaction_date = next(iter(dates))
            date.fromisoformat(transaction_date)
        except ValueError:
            return None, 'Invalid transaction date.'
        fields = ('source_id',) if kind == 'withdrawal' else ('destination_id',) if kind == 'deposit' else ('source_id', 'destination_id')
        accounts = {tuple(str(s.get(f) or '') for f in fields) for s in splits}
        if len(accounts) != 1 or not all(next(iter(accounts))):
            return None, 'Mixed or missing paying/receiving accounts; requires manual review.'
        try:
            amounts = [Decimal(str(s['amount'])) for s in splits]
            if any(not a.is_finite() or a <= 0 for a in amounts):
                raise ValueError()
            with localcontext() as ctx:
                ctx.prec = 50
                total = sum(amounts, Decimal(0))
        except (KeyError, ValueError, InvalidOperation):
            return None, 'Invalid split amount.'
        descriptions = sorted({' '.join((s.get('description') or '').casefold().split()) for s in splits} - {''})
        row = {'group_id': gid, 'title': group['attributes'].get('group_title') or splits[0].get('description') or gid,
               'date': transaction_date, 'type': kind, 'currency': next(iter(currencies)), 'total': str(total),
               'account_key': next(iter(accounts)), 'descriptions': descriptions,
               'external_ids': sorted({s['external_id'] for s in splits if s.get('external_id')}),
               'tags': sorted({tag for s in splits for tag in (s.get('tags') or [])}),
               'splits': [{'journal_id': str(s['transaction_journal_id']), 'description': s.get('description') or '',
                           'amount': s['amount'], 'source': s.get('source_name') or '',
                           'destination': s.get('destination_name') or ''} for s in splits]}
        return row, None
