"""Local Amazon order inbox and reviewed Firefly description and notes enrichment."""
import hashlib
import json
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from ..client import Problem


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def money(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n > Decimal('1000000000') or n.as_tuple().exponent < -12:
            raise ValueError()
        return str(n)
    except (InvalidOperation, ValueError, TypeError):
        raise Problem('Invalid Amazon amount.') from None


def day(value):
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        raise Problem('Invalid Amazon date.') from None


def marker(key):
    # Keep internal account routing out of Firefly notes.
    return '[Sidecar Amazon ' + digest(key)[:24] + ']'


def description(order):
    items = []
    for item in order['items']:
        title = item['title']
        if len(title) > 50: title = title[:47] + '...'
        try: multiple = Decimal(item['quantity']) > 1
        except InvalidOperation: multiple = False
        items.append((item['quantity'] + 'x ' if multiple else '') + title)
    value = 'Amazon ' + order['orderId'] + ': ' + ', '.join(items)
    return value if len(value) <= 1000 else value[:997] + '...'


class Amazon:
    def __init__(self, client, store, lock):
        self.client, self.store, self.lock = client, store, lock
        with store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS amazon_matches (key TEXT PRIMARY KEY, journal_id TEXT UNIQUE NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS amazon_orders (key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')

    def ingest(self, body):
        account = body.get('account', 'default')
        if not isinstance(account, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', account):
            raise Problem('Use an account label with letters, numbers, hyphens or underscores.')
        if body.get('marketplace', 'amazon.es') != 'amazon.es':
            raise Problem('This first version supports amazon.es only.')
        orders = body.get('orders')
        if not isinstance(orders, list) or len(orders) > 500:
            raise Problem('Send up to 500 orders per request.')
        normalized = []
        for raw in orders:
            if not isinstance(raw, dict) or not re.fullmatch(r'\d{3}-\d{7}-\d{7}', str(raw.get('orderId', ''))):
                raise Problem('Invalid Amazon order ID.')
            currency = raw.get('currency')
            if currency != 'EUR':
                raise Problem('Amazon Spain orders must use EUR.')
            items = raw.get('items', [])
            if not isinstance(items, list) or len(items) > 500:
                raise Problem('Invalid Amazon items.')
            clean_items = []
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get('title'), str) or len(item['title']) > 2000:
                    raise Problem('Invalid Amazon item title.')
                clean_items.append({'title': item['title'], 'asin': str(item.get('asin', ''))[:20], 'quantity': str(item.get('quantity', 1))[:10]})
            payments = raw.get('transactions') or []
            if not isinstance(payments, list) or len(payments) > 100:
                raise Problem('Invalid Amazon payments.')
            clean_payments = []
            for payment in payments:
                if not isinstance(payment, dict) or payment.get('currency', currency) != currency:
                    raise Problem('Invalid Amazon payment currency.')
                # Negative/explicit refund records are not withdrawal candidates.
                value = str(payment.get('amount'))
                negative = value.startswith('-')
                clean_payments.append({'date': day(payment.get('date')), 'amount': ('-' if negative else '') + money(value[1:] if negative else value)})
            order = dict(orderId=raw['orderId'], orderDate=day(raw.get('orderDate')), currency=currency,
                         totalAmount=money(raw.get('totalAmount')), items=clean_items,
                         chargedAmount=None if raw.get('chargedAmount') is None else money(raw['chargedAmount']),
                         transactions=sorted(clean_payments, key=lambda p: (p['date'], p['amount'])),
                         account=account, marketplace='amazon.es', orderStatus=str(raw.get('orderStatus', ''))[:100])
            key = account + ':amazon.es:' + order['orderId']
            normalized.append((key, json.dumps(order)))
        with self.lock, self.store.db() as db:
            for key, payload in normalized:
                db.execute('INSERT INTO amazon_orders(key,payload) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated=CURRENT_TIMESTAMP', (key, payload))
        return {'received': len(normalized)}

    def orders(self):
        with self.store.db() as db:
            return [dict(key=k, **json.loads(p)) for k, p in db.execute('SELECT key,payload FROM amazon_orders ORDER BY updated DESC,key')]

    def listing(self, start='', end='', days='7'):
        if not start or not end:
            raise Problem('Choose a Firefly transaction date range.')
        first, last = day(start), day(end)
        if first > last:
            raise Problem('Choose a valid date range.')
        try:
            tolerance = int(days)
            if not 0 <= tolerance <= 60: raise ValueError()
        except (ValueError, TypeError):
            raise Problem('Date tolerance must be 0–60 days.') from None
        groups = self.client.all('transactions', start=first, end=last, type='withdrawal')
        rows = []
        for group in groups:
            splits = group['attributes']['transactions']
            for split in splits:
                if split.get('type') != 'withdrawal' or not first <= day(split['date']) <= last:
                    continue
                rows.append(dict(split, group_id=str(group['id']), journal_id=str(split['transaction_journal_id']), journal_count=len(splits)))
        result = []
        with self.store.db() as db:
            bindings = dict(db.execute('SELECT key,journal_id FROM amazon_matches'))
        for order in self.orders():
            payments = order['transactions'] or [{'date': order['orderDate'], 'amount': order['chargedAmount'] if order['chargedAmount'] is not None else order['totalAmount']}]
            occurrences = {}
            for payment in payments:
                if Decimal(payment['amount']) <= 0: continue
                payment_hash = digest({'date':payment['date'],'amount':str(Decimal(payment['amount']).normalize())})[:16]
                ordinal = occurrences.get(payment_hash, 0)
                occurrences[payment_hash] = ordinal + 1
                key = order['key'] + ':' + payment_hash + ':' + str(ordinal)
                note_marker = marker(key)
                candidates = []
                for row in rows:
                    searchable = ' '.join(str(row.get(k) or '') for k in ('description', 'destination_name', 'notes', 'external_id'))
                    if ('amazon' not in searchable.lower() and order['orderId'] not in searchable): continue
                    if row.get('currency_code') != order['currency'] or Decimal(str(row['amount'])) != Decimal(payment['amount']): continue
                    delta = abs((date.fromisoformat(day(row['date'])) - date.fromisoformat(payment['date'])).days)
                    if delta > tolerance: continue
                    if key in bindings and bindings[key] != row['journal_id']: continue
                    if row['journal_id'] in bindings.values() and bindings.get(key) != row['journal_id']: continue
                    candidates.append(dict(row, distance=delta, applied=note_marker in (row.get('notes') or '') and row.get('description') == description(order)))
                result.append({'key': key, 'order': order, 'payment': payment, 'basis': 'payment' if order['transactions'] else 'charged amount' if order['chargedAmount'] is not None else 'order total (verify manually)', 'candidates': candidates})
        return {'orders': result, 'stored': len(self.orders())}

    def review(self, body):
        key, jid = body.get('key'), str(body.get('journal_id', ''))
        listing = self.listing(body.get('start'), body.get('end'), body.get('days', '7'))
        entry = next((r for r in listing['orders'] if r['key'] == key), None)
        row = next((r for r in (entry or {}).get('candidates', []) if r['journal_id'] == jid), None)
        if not row: raise Problem('Match is no longer available. Refresh Amazon Sync.', 409)
        group, split = self.client.journal(jid)
        note_marker = marker(key)
        legacy_marker = '[Sidecar Amazon ' + key + ']'
        text = note_marker + '\nAmazon.es order ' + entry['order']['orderId'] + '\n' + '\n'.join(i['quantity'] + ' × ' + i['title'] for i in entry['order']['items'])
        text += '\nhttps://www.amazon.es/gp/your-account/order-details?orderID=' + entry['order']['orderId']
        notes = split.get('notes') or ''
        if note_marker not in notes and legacy_marker not in notes and '[Sidecar Amazon ' in notes:
            raise Problem('This journal already has an Amazon match. Review it in Firefly before choosing another.', 409)
        notes = notes.replace(legacy_marker, note_marker)
        after = notes if note_marker in notes else (notes + '\n\n' + text).strip()
        if len(after) > 60000: raise Problem('Resulting notes are too long.')
        plan = {'id': str(uuid.uuid4()), 'kind': 'amazon', 'key': key, 'order_key': entry['order']['key'],
                'order_hash': digest(entry['order']), 'before': group, 'journal_id': jid, 'group_id': str(group['id']), 'notes': after, 'description': description(entry['order'])}
        self.store.save_operation(plan)
        return dict(plan, candidate=row, order=entry['order'])

    def apply(self, body):
        with self.lock:
            plan, state, result = self.store.operation(str(body.get('plan_id', '')), 'amazon')
            group, split = self.client.journal(plan['journal_id'])
            if 'description' not in plan:
                raise Problem('This review predates description enrichment. Create a new review.', 409)
            if split.get('notes') == plan['notes'] and split.get('description') == plan['description']:
                self.store.save_operation(plan, 'complete')
                return {'complete': True, 'group_id': plan['group_id']}
            if digest(group) != digest(plan['before']):
                raise Problem('Transaction changed since review. Refresh and review again.', 409)
            order = next((o for o in self.orders() if o['key'] == plan['order_key']), None)
            if digest(order) != plan['order_hash']:
                raise Problem('Amazon order changed since review. Review again.', 409)
            updates = [{'transaction_journal_id': str(s['transaction_journal_id']), **({'notes': plan['notes'], 'description': plan['description']} if str(s['transaction_journal_id']) == plan['journal_id'] else {})} for s in group['attributes']['transactions']]
            payload = {'apply_rules': False, 'fire_webhooks': False, 'transactions': updates}
            if len(updates) > 1: payload['group_title'] = group['attributes'].get('group_title')
            import sqlite3
            with self.store.db() as db:
                existing = db.execute('SELECT journal_id FROM amazon_matches WHERE key=?', (plan['key'],)).fetchone()
                if existing and existing[0] != plan['journal_id']:
                    raise Problem('This Amazon payment is already assigned to another journal.', 409)
                try:
                    db.execute('INSERT OR IGNORE INTO amazon_matches(key,journal_id) VALUES (?,?)', (plan['key'],plan['journal_id']))
                    actual = db.execute('SELECT journal_id FROM amazon_matches WHERE key=?', (plan['key'],)).fetchone()
                    if not actual or actual[0] != plan['journal_id']: raise sqlite3.IntegrityError()
                except sqlite3.IntegrityError:
                    raise Problem('This journal is already assigned to another Amazon payment.', 409) from None
            self.store.save_operation(plan, 'applying')
            self.client.request('PUT', 'transactions/' + plan['group_id'], payload, _sidecar_action='Enrich Amazon order')
            after_group, verified = self.client.journal(plan['journal_id'])
            if verified.get('notes') != plan['notes'] or verified.get('description') != plan['description']:
                raise Problem('Could not verify Amazon description and notes. Inspect Activity and Firefly before retrying.', 409)
            from .reimbursements import fingerprint
            before_splits = group['attributes']['transactions']
            after_splits = after_group['attributes']['transactions']
            protected = lambda row: dict(fingerprint(row), tags=row.get('tags'), budget_id=row.get('budget_id'), bill_id=row.get('bill_id'))
            expected = [dict(s, **({'description': plan['description']} if str(s['transaction_journal_id']) == plan['journal_id'] else {})) for s in before_splits]
            if [protected(s) for s in expected] != [protected(s) for s in after_splits]:
                raise Problem('Firefly changed other fields. Inspect Activity and the transaction.', 409)
            self.store.save_operation(plan, 'complete')
            return {'complete': True, 'group_id': plan['group_id']}
