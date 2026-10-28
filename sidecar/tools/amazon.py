"""Local Amazon order inbox and reviewed Firefly description and notes enrichment."""
import os
import copy
import hashlib
import json
import re
import uuid
import threading
import time
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from ..client import Problem


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def order_amount(order):
    if order['transactions']:
        return str(sum((Decimal(p['amount']) for p in order['transactions']), Decimal(0)))
    if order['chargedAmount'] is not None:
        return str(Decimal(order['chargedAmount']) + Decimal(order.get('giftCardAmount', '0')))
    return order['totalAmount']


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


def order_url(order):
    return 'https://www.amazon.es/gp/your-account/order-details?orderID=' + order['orderId']


def markdown_text(value):
    # Product titles are plain text, even when they contain Markdown or HTML.
    return re.sub(r'([\\`*_\[\]<>])', r'\\\1', value.replace('&', '&amp;'))


def note_block(order, key):
    items = ['- ' + item['quantity'] + ' x ' + markdown_text(' '.join(item['title'].splitlines())) for item in order['items']]
    return marker(key) + '  \nAmazon Order ' + order['orderId'] + '  \nItems:' + (('\n' + '\n'.join(items)) if items else '') + '\n\n[View Amazon order](' + order_url(order) + ')'


def enriched_notes(order, key, notes):
    block = note_block(order, key)
    current, legacy = marker(key), '[Sidecar Amazon ' + key + ']'
    if current not in notes and legacy not in notes:
        if '[Sidecar Amazon ' in notes:
            raise Problem('This journal already has an Amazon match. Review it in Firefly before choosing another.', 409)
        return (notes + '\n\n' + block).strip()
    for tag in (current, legacy):
        # Replace only a recognized generated block, retaining user text around it.
        patterns = [re.escape(tag) + r' {2}\nAmazon Order ' + re.escape(order['orderId']) + r' {2}\nItems:(?:\n- [^\n]*)*\n\n\[View Amazon order\]\(' + re.escape(order_url(order)) + r'\)',
                    re.escape(tag) + r'\nAmazon Order ' + re.escape(order['orderId']) + r'\n(?:\n)?Items:(?:\n• [^\n]*)*\n\n\[View Amazon order\]\(' + re.escape(order_url(order)) + r'\)',
                    re.escape(tag) + r'\n\nAmazon Order ' + re.escape(order['orderId']) + r'\n\nItems:(?:\n\n• [^\n]*)*',
                    re.escape(tag) + r'\nAmazon.es order ' + re.escape(order['orderId']) + r'\n.*?\nhttps://www\.amazon\.es/gp/your-account/order-details\?orderID=' + re.escape(order['orderId']) + r'(?=\n|$)']
        for pattern in patterns:
            match = re.search(pattern, notes, re.DOTALL)
            if match: return notes[:match.start()] + block + notes[match.end():]
    raise Problem('Existing Amazon notes were edited. Inspect them in Firefly before applying a new review.', 409)


class Amazon:
    def __init__(self, client, store, lock):
        self.client, self.store, self.lock = client, store, lock
        self.match_jobs = {}
        self.match_jobs_lock = threading.Lock()
        with store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS amazon_gift_jobs (reference TEXT PRIMARY KEY, plan_id TEXT NOT NULL)')
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
                         giftCardAmount=money(raw.get('giftCardAmount', 0)),
                         transactions=sorted(clean_payments, key=lambda p: (p['date'], p['amount'])),
                         account=account, marketplace='amazon.es', orderStatus=str(raw.get('orderStatus', ''))[:100])
            key = account + ':amazon.es:' + order['orderId']
            normalized.append((key, json.dumps(order)))
        with self.lock, self.store.db() as db:
            for key, payload in normalized:
                db.execute('INSERT INTO amazon_orders(key,payload) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated=CURRENT_TIMESTAMP', (key, payload))
        return {'received': len(normalized)}

    def status(self):
        orders = self.orders()
        dates = [o['orderDate'] for o in orders] + [p['date'] for o in orders for p in o['transactions']]
        with self.store.db() as db:
            enriched = set(db.execute("SELECT DISTINCT json_extract(payload,'$.order_key'),json_extract(payload,'$.order_hash') FROM operations WHERE kind IN ('amazon','amazon_manual') AND state='complete'"))
        pending = sum((order['key'],digest(order)) not in enriched for order in orders)
        return {'stored':len(orders), 'not_enriched':pending, 'start':min(dates) if dates else '', 'end':max(dates) if dates else '', 'revision':digest([orders,pending])}

    def orders(self):
        with self.store.db() as db:
            return [dict(key=k, **json.loads(p)) for k, p in db.execute("SELECT key,payload FROM amazon_orders ORDER BY json_extract(payload,'$.orderDate') DESC,key")]

    def listing(self, start='', end='', days='7', progress=None):
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
        groups = {}
        for kind in ('withdrawal','transfer'):
            if progress: progress({'phase':'loading','message':'Loading '+kind+' transactions from Firefly…','checked':0,'total':0})
            for group in self.client.all('transactions', start=first, end=last, type=kind):
                groups[str(group['id'])]=group
        groups=groups.values()
        rows = []
        for group in groups:
            splits = group['attributes']['transactions']
            for split in splits:
                if split.get('type') not in ('withdrawal','transfer') or not first <= day(split['date']) <= last:
                    continue
                rows.append(dict(split, group_id=str(group['id']), journal_id=str(split['transaction_journal_id']), journal_count=len(splits), group_title=group['attributes'].get('group_title')))
        result = []
        with self.store.db() as db:
            bindings = dict(db.execute('SELECT key,journal_id FROM amazon_matches'))
            enriched = set(db.execute("SELECT DISTINCT json_extract(payload,'$.order_key'),json_extract(payload,'$.order_hash') FROM operations WHERE kind IN ('amazon','amazon_manual') AND state='complete'"))
        orders=self.orders()
        if progress:progress({'phase':'matching','message':'Checking collected orders…','checked':0,'total':len(orders)})
        for index,order in enumerate(orders):
            manual_rows = [row for row in rows if bindings.get(order['key'] + ':manual:' + row['journal_id']) == row['journal_id'] and marker(order['key'] + ':manual:' + row['journal_id']) in (row.get('notes') or '')]
            with self.store.db() as db:
                gift_rows = db.execute("SELECT payload,result FROM operations WHERE kind='amazon_gift' AND state='complete' AND json_extract(payload,'$.order_key')=?", (order['key'],)).fetchall()
            gift_copies = [dict(json.loads(result), amount=json.loads(payload)['transaction']['amount'], currency=order['currency']) for payload,result in gift_rows]
            # Exported payment rows can contain both bank and gift-card charges.
            # The explicit charged amount is the bank payment to match.
            if order['chargedAmount'] is not None:
                charged = order['chargedAmount']
                matching = [p for p in order['transactions'] if Decimal(p['amount']) == Decimal(charged) and Decimal(p['amount']) > 0]
                payments = [{'date':matching[0]['date'] if matching else order['orderDate'], 'amount':charged}]
                basis = 'charged amount'
            else:
                payments = order['transactions'] or [{'date':order['orderDate'], 'amount':order['totalAmount']}]
                basis = 'payment' if order['transactions'] else 'order total (verify manually)'
            gift_amount = order.get('giftCardAmount', '0')
            if order['chargedAmount'] is not None and Decimal(order['chargedAmount']) == 0 and Decimal(gift_amount) > 0:
                payments = [{'date':order['orderDate'], 'amount':gift_amount, 'gift_card_only':True}]
            occurrences = {}
            for payment in payments:
                if Decimal(payment['amount']) <= 0: continue
                payment_hash = digest({'date':payment['date'],'amount':str(Decimal(payment['amount']).normalize())})[:16]
                ordinal = occurrences.get(payment_hash, 0)
                occurrences[payment_hash] = ordinal + 1
                key = order['key'] + ':' + payment_hash + ':' + str(ordinal)
                candidates = []
                for row in rows:
                    if payment.get('gift_card_only') or row.get('type') != 'withdrawal': continue
                    searchable = ' '.join(str(row.get(k) or '') for k in ('description', 'destination_name', 'notes', 'external_id'))
                    if ('amazon' not in searchable.lower() and order['orderId'] not in searchable): continue
                    if row.get('currency_code') != order['currency'] or Decimal(str(row['amount'])) != Decimal(payment['amount']): continue
                    delta = abs((date.fromisoformat(day(row['date'])) - date.fromisoformat(payment['date'])).days)
                    if delta > tolerance: continue
                    if key in bindings and bindings[key] != row['journal_id']: continue
                    if row['journal_id'] in bindings.values() and bindings.get(key) != row['journal_id']: continue
                    candidates.append(dict(row, distance=delta, applied=note_block(order, key) in (row.get('notes') or '') and row.get('description') == description(order) and (row['journal_count'] == 1 or row.get('group_title') == description(order))))
                result.append({'key': key, 'order': order, 'payment': payment, 'display_total':order_amount(order), 'basis': 'gift card (manual selection)' if payment.get('gift_card_only') else basis, 'candidates': candidates, 'manual_journals': manual_rows, 'gift_copies': gift_copies, 'enriched':(order['key'],digest(order)) in enriched or bool(manual_rows) or any(c['applied'] for c in candidates)})
            if progress:progress({'phase':'matching','message':'Checking collected orders…','checked':index+1,'total':len(orders)})
        counts=self.status()
        return {'orders': result, 'stored':counts['stored'], 'not_enriched':counts['not_enriched']}

    def start_matches(self, body):
        filters={key:body.get(key,'7' if key=='days' else '') for key in ('start','end','days')}
        with self.match_jobs_lock:
            now=time.monotonic()
            self.match_jobs={key:job for key,job in self.match_jobs.items() if job['state']=='running' or now-job['created']<600}
            if any(job['state']=='running' for job in self.match_jobs.values()):
                raise Problem('Amazon matching is already running. Wait for it to finish.',409)
            while len(self.match_jobs)>=5:
                del self.match_jobs[next(iter(self.match_jobs))]
            job_id=uuid.uuid4().hex
            self.match_jobs[job_id]={'created':now,'state':'running','phase':'loading','message':'Preparing match search…','checked':0,'total':0}
        def update(progress):
            with self.match_jobs_lock:self.match_jobs[job_id].update(progress)
        def work():
            try:
                result=self.listing(**filters,progress=update)
                with self.match_jobs_lock:self.match_jobs[job_id].update(state='complete',result=result,message='Match search complete.')
            except Exception as error:
                with self.match_jobs_lock:self.match_jobs[job_id].update(state='failed',error=str(error) if isinstance(error,Problem) else 'Amazon match search failed. Try again.')
        threading.Thread(target=work,daemon=True).start()
        return {'id':job_id}

    def match_status(self, job_id):
        with self.match_jobs_lock:
            job=self.match_jobs.get(job_id)
            if not job or time.monotonic()-job['created']>=600 and job['state']!='running':
                raise Problem('Match search expired. Find matches again.',404)
            return copy.deepcopy({key:value for key,value in job.items() if key!='created'})

    def review(self, body):
        key, jid = body.get('key'), str(body.get('journal_id', ''))
        listing = self.listing(body.get('start'), body.get('end'), body.get('days', '7'))
        entry = next((r for r in listing['orders'] if r['key'] == key), None)
        row = next((r for r in (entry or {}).get('candidates', []) if r['journal_id'] == jid), None)
        if not row: raise Problem('Match is no longer available. Refresh Amazon Sync.', 409)
        group, split = self.client.journal(jid)
        after = enriched_notes(entry['order'], key, split.get('notes') or '')
        if len(after) > 60000: raise Problem('Resulting notes are too long.')
        plan = {'id': str(uuid.uuid4()), 'kind': 'amazon', 'key': key, 'order_key': entry['order']['key'],
                'order_hash': digest(entry['order']), 'before': group, 'journal_id': jid, 'group_id': str(group['id']), 'notes': after, 'description': description(entry['order']), 'group_title': description(entry['order']) if len(group['attributes']['transactions']) > 1 else group['attributes'].get('group_title'), 'format_version': 4}
        self.store.save_operation(plan)
        return dict(plan, candidate=row, order=entry['order'])

    def apply(self, body):
        with self.lock:
            plan, state, result = self.store.operation(str(body.get('plan_id', '')), 'amazon')
            group, split = self.client.journal(plan['journal_id'])
            if plan.get('format_version') != 4:
                raise Problem('This review predates the current Amazon format. Create a new review.', 409)
            if split.get('notes') == plan['notes'] and split.get('description') == plan['description'] and group['attributes'].get('group_title') == plan['group_title']:
                self.store.save_operation(plan, 'complete')
                return {'complete': True, 'group_id': plan['group_id']}
            if digest(group) != digest(plan['before']):
                raise Problem('Transaction changed since review. Refresh and review again.', 409)
            order = next((o for o in self.orders() if o['key'] == plan['order_key']), None)
            if digest(order) != plan['order_hash']:
                raise Problem('Amazon order changed since review. Review again.', 409)
            updates = [{'transaction_journal_id': str(s['transaction_journal_id']), **({'notes': plan['notes'], 'description': plan['description']} if str(s['transaction_journal_id']) == plan['journal_id'] else {})} for s in group['attributes']['transactions']]
            payload = {'apply_rules': False, 'fire_webhooks': False, 'transactions': updates}
            if len(updates) > 1: payload['group_title'] = plan['group_title']
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
            if verified.get('notes') != plan['notes'] or verified.get('description') != plan['description'] or after_group['attributes'].get('group_title') != plan['group_title']:
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


    def order(self, key):
        order = next((row for row in self.orders() if row['key'] == key), None)
        if not order: raise Problem('Order not found. Refresh Amazon Sync.', 404)
        return order

    def matchable_payment(self, split, currency):
        gift_id = os.environ.get('AMAZON_GIFT_CARD_ACCOUNT_ID', '').strip()
        return split.get('currency_code') == currency and (split.get('type') == 'withdrawal' or
            (split.get('type') == 'transfer' and bool(gift_id) and str(split.get('destination_id')) == gift_id))

    def manual_options(self, body):
        order = self.order(body.get('order_key'))
        order_day = date.fromisoformat(order['orderDate'])
        start = day(body.get('start') or (order_day-timedelta(days=3)).isoformat())
        end = day(body.get('end') or (order_day+timedelta(days=3)).isoformat())
        if start > end: raise Problem('Choose a valid date range.')
        rows = []
        groups = {str(group['id']):group for kind in ('withdrawal','transfer')
                  for group in self.client.all('transactions', type=kind, start=start, end=end)}
        for group in groups.values():
            splits = group['attributes']['transactions']
            for split in splits:
                if self.matchable_payment(split, order['currency']) and start <= day(split['date']) <= end:
                    rows.append(dict(split, journal_id=str(split['transaction_journal_id']), group_id=str(group['id']), journal_count=len(splits), group_title=group['attributes'].get('group_title')))
        rows.sort(key=lambda row: day(row['date']), reverse=True)
        if len(rows) > 1000: raise Problem('Choose a narrower date range (more than 1,000 journals).')
        return {'order': order, 'display_total':order_amount(order), 'start':start, 'end':end, 'journals': rows, 'gift_card_configured': bool(os.environ.get('AMAZON_GIFT_CARD_ACCOUNT_ID')),
                'gift_card_tag': os.environ.get('AMAZON_GIFT_CARD_TAG', 'Paid by Gift Card')}

    def manual_review(self, body):
        order = self.order(body.get('order_key'))
        ids = body.get('journal_ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 30 or any(not isinstance(j, str) or not j.isascii() or not j.isdigit() for j in ids) or len(set(ids)) != len(ids):
            raise Problem('Choose 1–30 different paying journals.')
        groups, rows = {}, []
        with self.lock:
            for jid in ids:
                group, split = self.client.journal(jid)
                if not self.matchable_payment(split, order['currency']):
                    raise Problem('Select a withdrawal or a transfer into the configured gift-card account in the order currency.', 409)
                key = order['key'] + ':manual:' + jid
                notes = enriched_notes(order, key, split.get('notes') or '')
                if len(notes) > 60000: raise Problem('Resulting notes are too long.')
                groups[str(group['id'])] = group
                rows.append(dict(split, group_id=str(group['id']), journal_id=jid, journal_count=len(group['attributes']['transactions']), key=key, new_notes=notes))
            total = sum(Decimal(str(row['amount'])) for row in rows)
            if total <= 0: raise Problem('Selected journals must have positive amounts.')
            plan = {'id': str(uuid.uuid4()), 'kind': 'amazon_manual', 'order_key': order['key'], 'order_hash': digest(order),
                    'description': description(order), 'groups': groups, 'rows': rows, 'total': str(total),
                    'order_total': order['chargedAmount'] if order['chargedAmount'] is not None else order['totalAmount'], 'currency': order['currency'], 'format_version': 4}
            self.store.save_operation(plan)
            return plan

    def manual_apply(self, body):
        from .reimbursements import fingerprint
        import sqlite3
        with self.lock:
            plan, _, _ = self.store.operation(str(body.get('plan_id', '')), 'amazon_manual')
            if plan.get('format_version') != 4: raise Problem('This review predates Markdown notes. Create a new manual review.', 409)
            if digest(self.order(plan['order_key'])) != plan['order_hash']:
                raise Problem('Order changed. Create a new manual review.', 409)
            # Validate every parent before reserving assignments or making writes.
            for gid, before in plan['groups'].items():
                current = self.client.request('GET', 'transactions/' + gid)['data']
                selected = {r['journal_id']:r for r in plan['rows'] if r['group_id']==gid}
                already = all(any(str(s['transaction_journal_id'])==jid and s.get('notes')==row['new_notes'] and s.get('description')==plan['description'] for s in current['attributes']['transactions']) for jid,row in selected.items())
                already = already and (len(current['attributes']['transactions'])==1 or current['attributes'].get('group_title')==plan['description'])
                if not already and digest(current)!=digest(before):
                    raise Problem('A paying transaction changed. Review the selection again.', 409)
            # Reserve every journal atomically before any remote write.
            with self.store.db() as db:
                for row in plan['rows']:
                    existing = db.execute('SELECT key FROM amazon_matches WHERE journal_id=?', (row['journal_id'],)).fetchone()
                    if existing and existing[0] != row['key']: raise Problem('A selected journal is already assigned to another Amazon match.', 409)
                    try: db.execute('INSERT OR IGNORE INTO amazon_matches VALUES (?,?)', (row['key'], row['journal_id']))
                    except sqlite3.IntegrityError: raise Problem('A selected journal is already assigned.', 409) from None
            completed = []
            for gid, before in plan['groups'].items():
                selected = {r['journal_id']: r for r in plan['rows'] if r['group_id'] == gid}
                current = self.client.request('GET', 'transactions/' + gid)['data']
                splits = current['attributes']['transactions']
                done = all(any(str(s['transaction_journal_id']) == jid and s.get('description') == plan['description'] and s.get('notes') == row['new_notes'] for s in splits) for jid, row in selected.items())
                done = done and (len(splits) == 1 or current['attributes'].get('group_title') == plan['description'])
                if not done:
                    if digest(current) != digest(before): raise Problem('A paying transaction changed. Inspect Activity and review the remaining journals again.', 409)
                    patches = []
                    expected = []
                    for split in splits:
                        jid = str(split['transaction_journal_id'])
                        patch = {'transaction_journal_id': jid}
                        if jid in selected: patch.update(description=plan['description'], notes=selected[jid]['new_notes'])
                        patches.append(patch); expected.append(dict(split, **{k:v for k,v in patch.items() if k != 'transaction_journal_id'}))
                    payload = {'apply_rules':False, 'fire_webhooks':False, 'transactions':patches}
                    if len(splits) > 1: payload['group_title'] = plan['description']
                    self.store.save_operation(plan, 'applying', {'completed': completed})
                    self.client.request('PUT', 'transactions/' + gid, payload, _sidecar_action='Match Amazon paying journals')
                    after = self.client.request('GET', 'transactions/' + gid)['data']
                    protected = lambda row: dict(fingerprint(row), notes=row.get('notes'), tags=row.get('tags'), budget_id=row.get('budget_id'), bill_id=row.get('bill_id'))
                    if [protected(r) for r in after['attributes']['transactions']] != [protected(r) for r in expected] or (len(splits)>1 and after['attributes'].get('group_title')!=plan['description']):
                        raise Problem('Manual match verification failed. Inspect Activity before retrying.', 409)
                completed.append(gid)
            result = {'complete': True, 'group_ids': completed}
            self.store.save_operation(plan, 'complete', result)
            return result

    def gift_options(self, body):
        order = self.order(body.get('order_key'))
        if Decimal(order.get('giftCardAmount', '0')) <= 0: raise Problem('This order has no exported gift-card payment. Sync it again if its payment details changed.', 409)
        account, tag, _ = self.gift_configuration({'currency_code':order['currency']}, False)
        from .validation import Validation
        options = {'account':account, 'tag':tag, 'description':description(order), 'date':order['orderDate'], 'amount':order['giftCardAmount']}
        for endpoint in ('accounts','categories','budgets','bills'):
            entries = self.client.all(endpoint, **({'type':'all'} if endpoint=='accounts' else {}))
            options[endpoint] = [{'id':str(row['id']), 'name':row['attributes'].get('name') or str(row['id'])}
                for row in entries if row['attributes'].get('active') is not False and
                (endpoint!='accounts' or Validation.account_type(row['attributes'].get('type')) in ('expense','cash'))]
        return options

    def gift_configuration(self, split, require_related=True):
        account_id = os.environ.get('AMAZON_GIFT_CARD_ACCOUNT_ID', '').strip()
        tag = os.environ.get('AMAZON_GIFT_CARD_TAG', 'Paid by Gift Card').strip()
        if not account_id.isascii() or not account_id.isdigit() or not tag or len(tag)>255:
            raise Problem('Configure AMAZON_GIFT_CARD_ACCOUNT_ID and AMAZON_GIFT_CARD_TAG on the sidecar.', 409)
        account = next((a for a in self.client.all('accounts', type='asset') if str(a['id']) == account_id), None)
        if not account or account['attributes'].get('type') != 'asset' or account['attributes'].get('active') is False:
            raise Problem('The configured gift-card account must be an active asset account.', 409)
        if account['attributes'].get('currency_code') not in (None, '', split.get('currency_code')):
            raise Problem('The gift-card account must use the selected journal currency.', 409)
        if account_id in (str(split.get('source_id')), str(split.get('destination_id'))):
            raise Problem('Choose a paying journal from a different account than the gift-card account.', 409)
        if not require_related: return account, tag, None
        related = next((t for t in self.client.all('link-types') if t['attributes']['name'].lower() == 'related'), None)
        if not related: raise Problem('Enable the Related transaction link type in Firefly.', 409)
        return account, tag, str(related['id'])

    def gift_review(self, body):
        from .reimbursements import identifier
        order = self.order(body.get('order_key'))
        if Decimal(order.get('giftCardAmount', '0')) <= 0: raise Problem('This order has no exported gift-card payment.', 409)
        if body.get('journal_ids') and (not isinstance(body['journal_ids'], list) or len(body['journal_ids'])>1): raise Problem('Select at most one related journal.')
        jid = identifier(body['journal_id']) if body.get('journal_id') else None
        with self.lock:
            if jid:
                group, split = self.client.journal(jid)
            else:
                options = self.gift_options(body)
                details = body.get('transaction')
                if not isinstance(details, dict): raise Problem('Enter the new withdrawal details.')
                title = details.get('description')
                if not isinstance(title, str) or not title.strip() or len(title)>1000: raise Problem('Enter a description of up to 1,000 characters.')
                split = {'type':'withdrawal', 'currency_code':order['currency'], 'date':day(details.get('date')),
                         'amount':money(body.get('amount')), 'description':title.strip(), 'tags':[], 'notes':note_block(order, order['key']+':gift')}
                for field, endpoint in (('destination_id','accounts'),('category_id','categories'),('budget_id','budgets'),('bill_id','bills')):
                    value = str(details.get(field) or '')
                    if value and value not in {r['id'] for r in options[endpoint]}: raise Problem('Selected '+endpoint+' choice is unavailable.', 409)
                    if field=='destination_id' and not value: raise Problem('Choose a destination account.')
                    if value: split[field] = value
                split['destination_name'] = next(r['name'] for r in options['accounts'] if r['id']==split['destination_id'])
                group = None
            if split.get('type') != 'withdrawal' or split.get('currency_code') != order['currency'] or Decimal(str(split['amount'])) <= 0:
                raise Problem('Select a withdrawal journal in the order currency.', 409)
            amount = Decimal(money(body.get('amount', order['giftCardAmount']))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            places = int(split.get('currency_decimal_places', 2))
            if not 0 <= places <= 12 or amount <= 0 or amount != amount.quantize(Decimal(1).scaleb(-places)):
                raise Problem('Enter a positive gift-card amount with the currency precision.')
            account, tag, related = self.gift_configuration(split, bool(jid))
            reference = 'sidecar-amazon-gift-' + digest([order['key'], jid, str(account['id'])])[:32]
            with self.store.db() as db: saved = db.execute('SELECT plan_id FROM amazon_gift_jobs WHERE reference=?', (reference,)).fetchone()
            if saved:
                plan, state, result = self.store.operation(saved[0], 'amazon_gift')
                if Decimal(plan['transaction']['amount']) != amount:
                    raise Problem('A gift-card copy for this order and journal already uses a different amount. Inspect that transaction before changing it.', 409)
                if not jid and any(str(plan['transaction'].get(field) or '') != str(split.get(field) or '') for field in ('description','date','destination_id','category_id','budget_id','bill_id')):
                    raise Problem('A gift-card withdrawal for this order was already submitted with different details. Inspect Activity.', 409)
                return dict(plan, resume=True, state=state, result=result)
            fields = ('type','date','amount','description','currency_id','currency_code','foreign_currency_id','foreign_amount',
                      'destination_id','notes','category_id','budget_id','bill_id','tags','reconciled',
                      'interest_date','book_date','process_date','due_date','payment_date','invoice_date',
                      'sepa_cc','sepa_ct_op','sepa_ct_id','sepa_db','sepa_country','sepa_ep','sepa_ci','sepa_batch_id')
            copied = {k:copy.deepcopy(split[k]) for k in fields if split.get(k) is not None}
            copied['amount'] = str(amount)
            if split.get('foreign_amount') not in (None, ''):
                foreign_places = int(split.get('foreign_currency_decimal_places', 2))
                if not 0 <= foreign_places <= 12: raise Problem('Invalid foreign currency precision.')
                foreign = (Decimal(str(split['foreign_amount'])) * amount / Decimal(str(split['amount']))).quantize(Decimal(1).scaleb(-foreign_places), rounding=ROUND_HALF_UP)
                if foreign <= 0: raise Problem('The gift-card amount is too small in the foreign currency.')
                copied['foreign_amount'] = str(foreign)
            copied.update(source_id=str(account['id']), tags=list(dict.fromkeys((split.get('tags') or [])+[tag])), external_id=reference)
            plan = {'id':str(uuid.uuid4()), 'kind':'amazon_gift', 'order_key':order['key'], 'order_hash':digest(order),
                    'before':group, 'journal_id':jid, 'group_id':str(group['id']) if group else None, 'journal_count':len(group['attributes']['transactions']) if group else 1,
                    'original':split, 'transaction':copied, 'account':account, 'tag':tag, 'related_type_id':related, 'reference':reference}
            self.store.save_operation(plan)
            return plan

    def gift_apply(self, body):
        with self.lock:
            plan, state, result = self.store.operation(str(body.get('plan_id', '')), 'amazon_gift')
            with self.store.db() as db:
                saved = db.execute('SELECT plan_id FROM amazon_gift_jobs WHERE reference=?', (plan['reference'],)).fetchone()
            if saved and saved[0] != plan['id']:
                prior, _, _ = self.store.operation(saved[0], 'amazon_gift')
                if Decimal(prior['transaction']['amount']) != Decimal(plan['transaction']['amount']):
                    raise Problem('Another reviewed amount was already submitted for this gift-card copy. Inspect Activity.', 409)
                return self.gift_apply({'plan_id':saved[0]})
            # Locate prior creations by the generated import reference, including after lost responses.
            found = []
            for group in self.client.all('transactions', type='withdrawal', start=day(plan['transaction']['date']), end=day(plan['transaction']['date'])):
                for split in group['attributes']['transactions']:
                    if split.get('external_id') == plan['reference']: found.append((group, split))
            if len(found)>1: raise Problem('Multiple gift-card copies found. Inspect Firefly and Activity.', 409)
            if not found:
                if state not in ('review',):
                    raise Problem('The previous creation is unconfirmed. Inspect Activity; retry will only recover a confirmed copy and will not create another.', 409)
                current = self.client.journal(plan['journal_id'])[0] if plan['journal_id'] else None
                if digest(current) != digest(plan['before']) or digest(self.order(plan['order_key'])) != plan['order_hash']:
                    raise Problem('The source transaction or order changed. Create a new gift-card review.', 409)
                if not plan['journal_id']:
                    options = self.gift_options({'order_key':plan['order_key']})
                    for field, endpoint in (('destination_id','accounts'),('category_id','categories'),('budget_id','budgets'),('bill_id','bills')):
                        value = plan['transaction'].get(field)
                        if value and value not in {r['id'] for r in options[endpoint]}: raise Problem('Withdrawal choices changed. Review again.', 409)
                account, tag, related = self.gift_configuration(plan['original'], bool(plan['journal_id']))
                if str(account['id']) != str(plan['account']['id']) or tag != plan['tag'] or related != plan['related_type_id']:
                    raise Problem('Gift-card configuration changed. Review again.', 409)
                with self.store.db() as db:
                    db.execute('INSERT OR IGNORE INTO amazon_gift_jobs VALUES (?,?)', (plan['reference'],plan['id']))
                self.store.save_operation(plan, 'creating')
                # Mark creating before the request; any failed response is potentially an accepted write.
                created = self.client.request('POST', 'transactions', {'apply_rules':False,'fire_webhooks':False,'error_if_duplicate_hash':True,'transactions':[plan['transaction']]}, _sidecar_action='Create Amazon gift-card withdrawal')['data']
                if len(created['attributes']['transactions']) != 1: raise Problem('Unexpected created transaction. Inspect Activity.', 409)
                found = [(created, created['attributes']['transactions'][0])]
            created, split = found[0]
            expected = plan['transaction']
            for key in ('type','description','source_id','destination_id','currency_id','foreign_currency_id','category_id','budget_id','bill_id','notes','external_id'):
                if str(split.get(key) or '') != str(expected.get(key) or ''): raise Problem('Gift-card copy verification failed for '+key+'. Inspect Activity.', 409)
            for key in ('amount','foreign_amount'):
                if Decimal(str(split.get(key) or 0)) != Decimal(str(expected.get(key) or 0)): raise Problem('Gift-card copy amount changed. Inspect Activity.', 409)
            if day(split['date']) != day(expected['date']) or sorted(split.get('tags') or []) != sorted(expected['tags']): raise Problem('Gift-card copy details changed. Inspect Activity.', 409)
            jid = str(split['transaction_journal_id'])
            if not plan['journal_id']:
                result = {'group_id':str(created['id']), 'journal_id':jid, 'complete':True}
                self.store.save_operation(plan, 'complete', result)
                return result
            links = self.client.all('transaction-journals/' + plan['journal_id'] + '/links')
            linked = any(str(l['attributes'].get('link_type_id')) == plan['related_type_id'] and {str(l['attributes'].get('inward_id')),str(l['attributes'].get('outward_id'))} == {jid,plan['journal_id']} for l in links)
            result = {'group_id':str(created['id']), 'journal_id':jid, 'original_group_id':plan['group_id']}
            if not linked:
                if state in ('linking','complete'):
                    raise Problem('Related link is unconfirmed or was removed. Inspect Activity before retrying.', 409)
                self.store.save_operation(plan, 'linking', result)
                self.client.request('POST', 'transaction-links', {'link_type_id':plan['related_type_id'], 'inward_id':plan['journal_id'], 'outward_id':jid, 'notes':'Firefly Sidecar Amazon gift-card payment'}, _sidecar_action='Relate Amazon gift-card withdrawal')
                links = self.client.all('transaction-journals/' + plan['journal_id'] + '/links')
                if not any(str(l['attributes'].get('link_type_id')) == plan['related_type_id'] and {str(l['attributes'].get('inward_id')),str(l['attributes'].get('outward_id'))} == {jid,plan['journal_id']} for l in links):
                    raise Problem('Could not verify Related link. Inspect Activity.', 409)
            result['complete'] = True
            self.store.save_operation(plan, 'complete', result)
            return result
