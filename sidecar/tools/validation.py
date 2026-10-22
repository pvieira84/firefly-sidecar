import os
import secrets
import time
import copy
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from ..client import Problem
from .reimbursements import identifier, fingerprint
from .duplicates import Duplicates


class Validation:
    """Review queue; actions operate on individual journals, including unsplit transactions."""
    def __init__(self, client, lock):
        self.client, self.lock = client, lock
        self.deletion_previews = {}
        self.refund_previews = {}
        self.tag = os.environ.get('TODO_TAG', 'todo')
        if not self.tag.strip():
            raise ValueError('TODO_TAG must not be empty.')

    def listing(self):
        rows = {}
        for group in self.client.all('tags/' + quote(self.tag, safe='') + '/transactions'):
            for split in group['attributes']['transactions']:
                if self.tag in (split.get('tags') or []):
                    jid = str(split['transaction_journal_id'])
                    rows[jid] = dict(split, journal_id=jid, group_id=str(group['id']),
                                    group_title=group['attributes'].get('group_title') or '')
        checks = Duplicates(self.client).for_review(sorted({row['group_id'] for row in rows.values()}))
        for row in rows.values():
            row['duplicate_check'] = checks[row['group_id']]
        return {'tag': self.tag, 'transactions': sorted(rows.values(),
                key=lambda row: (row.get('created_at') or row.get('date') or '', row['journal_id']), reverse=True)}

    def complete(self, body):
        jid = identifier(body.get('journal_id'))
        with self.lock:
            group, current = self.client.journal(jid)
            if self.tag not in (current.get('tags') or []):
                return {'journal_id': jid, 'complete': True}
            updates = []
            for sibling in group['attributes']['transactions']:
                patch = {'transaction_journal_id': str(sibling['transaction_journal_id'])}
                if patch['transaction_journal_id'] == jid:
                    patch['tags'] = [tag for tag in (current.get('tags') or []) if tag != self.tag]
                updates.append(patch)
            payload = {'apply_rules': False, 'fire_webhooks': False, 'transactions': updates}
            if len(updates) > 1:
                payload['group_title'] = group['attributes'].get('group_title')
            self.client.request('PUT', 'transactions/' + str(group['id']), payload)
            _, verified = self.client.journal(jid)
            if self.tag in (verified.get('tags') or []):
                raise Problem('The todo tag is still present. Reload the queue before retrying.', 502)
            if (fingerprint(verified) != fingerprint(current) or
                    sorted(verified.get('tags') or []) != sorted(t for t in (current.get('tags') or []) if t != self.tag)):
                raise Problem('Firefly changed other fields during validation. Inspect the transaction in Firefly.', 409)
            return {'journal_id': jid, 'complete': True}

    def delete_preview(self, body):
        gid = identifier(body.get('group_id'))
        with self.lock:
            group = self.client.request('GET', 'transactions/' + gid)['data']
            now = time.monotonic()
            self.deletion_previews = {k: v for k, v in self.deletion_previews.items() if now-v['created'] < 600}
            if len(self.deletion_previews) >= 100:
                raise Problem('Too many pending deletion previews. Wait a few minutes and retry.', 429)
            token = secrets.token_urlsafe(32)
            self.deletion_previews[token] = {'created': now, 'group_id': gid, 'snapshot': copy.deepcopy(group)}
            return {'token': token, 'group_id': gid, 'transaction': group}

    def delete(self, body):
        token = body.get('token')
        if not isinstance(token, str) or len(token) > 100:
            raise Problem('Open the delete preview before confirming.', 400)
        with self.lock:
            preview = self.deletion_previews.get(token)
            if not preview or time.monotonic()-preview['created'] >= 600:
                raise Problem('Deletion preview expired. Open a new preview.', 409)
            gid = preview['group_id']
            current = self.client.request('GET', 'transactions/' + gid)['data']
            if current != preview['snapshot']:
                del self.deletion_previews[token]
                raise Problem('Transaction changed since the deletion preview. Reload and review again.', 409)
            self.client.request('DELETE', 'transactions/' + gid)
            del self.deletion_previews[token]
            return {'deleted': True, 'group_id': gid}

    def cash_account(self):
        configured = os.environ.get('CASH_ACCOUNT_ID', '').strip()
        if configured:
            identifier(configured)
            accounts = [self.client.request('GET', 'accounts/' + configured)['data']]
        else:
            accounts = self.client.all('accounts', type='cash')
        accounts = [a for a in accounts if a['attributes'].get('type') in ('cash', 'Cash account')]
        if len(accounts) != 1:
            raise Problem('Could not identify one Cash account. Set CASH_ACCOUNT_ID to the Firefly Cash account ID.', 409)
        return str(accounts[0]['id'])

    def mark_cash(self, body):
        jid = identifier(body.get('journal_id'))
        with self.lock:
            group, current = self.client.journal(jid)
            kind = current.get('type')
            if kind not in ('withdrawal', 'deposit', 'transfer'):
                raise Problem('Mark as cash supports withdrawals, deposits and transfers.', 409)
            changes = {'category_id': None, 'category_name': None, 'budget_id': None,
                       'budget_name': None, 'bill_id': None, 'bill_name': None}
            if kind != 'transfer':
                changes['destination_id' if kind == 'withdrawal' else 'source_id'] = self.cash_account()
            updates = []
            for sibling in group['attributes']['transactions']:
                patch = {'transaction_journal_id': str(sibling['transaction_journal_id'])}
                if patch['transaction_journal_id'] == jid:
                    patch.update(changes)
                updates.append(patch)
            payload = {'apply_rules': False, 'fire_webhooks': False, 'transactions': updates}
            if len(updates) > 1:
                payload['group_title'] = group['attributes'].get('group_title')
            self.client.request('PUT', 'transactions/' + str(group['id']), payload)
            _, verified = self.client.journal(jid)
            if any(verified.get(key) not in (None, '', 0, '0') for key in
                   ('category_id', 'category_name', 'budget_id', 'budget_name', 'bill_id', 'bill_name')):
                raise Problem('Firefly did not clear category, budget or subscription. Inspect the transaction before retrying.', 409)
            if any(str(verified.get(key)) != str(value) for key, value in changes.items() if key in ('source_id', 'destination_id')):
                raise Problem('Firefly did not apply the cash account. Inspect the transaction before retrying.', 409)
            expected = fingerprint(current)
            actual = fingerprint(verified)
            ignored = {'category_id', 'category_name'} | ({'destination_id'} if kind == 'withdrawal' else {'source_id'} if kind == 'deposit' else set())
            if (any(expected[key] != actual[key] for key in expected if key not in ignored) or
                    sorted(verified.get('tags') or []) != sorted(current.get('tags') or [])):
                raise Problem('Firefly changed other transaction fields. Inspect the transaction before retrying.', 409)
            return {'journal_id': jid, 'complete': True}

    def refund_candidates(self, body):
        jid = identifier(body.get('deposit_id'))
        with self.lock:
            parent, deposit = self.client.journal(jid)
            if deposit.get('type') != 'deposit':
                raise Problem('Only deposits can be marked as refunds.', 409)
            try:
                deposited = date.fromisoformat(deposit['date'][:10])
                lookback = int(os.environ.get('REFUND_LOOKBACK_DAYS', '90'))
                if not 0 <= lookback <= 3650:
                    raise ValueError()
                start = date.fromisoformat(body.get('start') or (deposited-timedelta(days=lookback)).isoformat())
                end = date.fromisoformat(body.get('end') or deposited.isoformat())
                tolerance = Decimal(str(body.get('tolerance', os.environ.get('REFUND_AMOUNT_TOLERANCE', '1.00'))))
                total = Decimal(deposit['amount'])
                if start > end or not tolerance.is_finite() or tolerance < 0 or not total.is_finite() or total <= 0:
                    raise ValueError()
            except (ValueError, InvalidOperation, TypeError):
                raise Problem('Choose valid dates and a nonnegative amount tolerance; check refund defaults.') from None
            candidates, snapshots, skipped = [], {}, []
            seen = set()
            for group in self.client.all('transactions', type='withdrawal', start=start.isoformat(), end=end.isoformat()):
                gid = str(group['id'])
                if gid in seen:
                    continue
                seen.add(gid)
                row, reason = Duplicates.summarize(gid, group)
                if reason:
                    skipped.append({'group_id': gid, 'reason': reason})
                    continue
                if (row['type'] != 'withdrawal' or row['currency'] != deposit['currency_code'] or
                        not start <= date.fromisoformat(row['date']) <= end or abs(Decimal(row['total'])-total) > tolerance):
                    continue
                row['difference'] = str(Decimal(row['total'])-total)
                candidates.append(row)
                snapshots[gid] = copy.deepcopy(group)
            candidates.sort(key=lambda r: (abs(Decimal(r['difference'])), r['date'], r['group_id']))
            now = time.monotonic()
            self.refund_previews = {k:v for k,v in self.refund_previews.items() if now-v['created'] < 600}
            if len(self.refund_previews) >= 50:
                raise Problem('Too many pending refund searches. Close old searches and retry later.', 429)
            token = secrets.token_urlsafe(32)
            self.refund_previews[token] = {'created': now, 'deposit': copy.deepcopy(deposit), 'candidates': snapshots}
            return {'token': token, 'deposit': dict(deposit, group_id=str(parent['id'])), 'candidates': candidates,
                    'start': start.isoformat(), 'end': end.isoformat(), 'tolerance': str(tolerance), 'skipped': skipped}

    def mark_refund(self, body):
        token = body.get('token')
        gid = identifier(body.get('group_id'))
        remove_todo = body.get('remove_todo', False)
        if not isinstance(token, str) or len(token)>100 or not isinstance(remove_todo, bool):
            raise Problem('Invalid refund selection.')
        with self.lock:
            preview = self.refund_previews.get(token)
            if not preview or time.monotonic()-preview['created'] >= 600:
                raise Problem('Refund search expired. Load the withdrawals again.', 409)
            if gid not in preview['candidates']:
                raise Problem('Choose a withdrawal from the current search.', 409)
            deposit = preview['deposit']
            deposit_id = str(deposit['transaction_journal_id'])
            _, current_deposit = self.client.journal(deposit_id)
            original = preview['candidates'][gid]
            current = self.client.request('GET', 'transactions/'+gid)['data']
            def financials(group):
                return {str(s['transaction_journal_id']):fingerprint(s) for s in group['attributes']['transactions']}
            if fingerprint(current_deposit) != fingerprint(deposit) or financials(current) != financials(original):
                raise Problem('Deposit or withdrawal changed since search. Load withdrawals again.', 409)
            kind = next((item for item in self.client.all('link-types') if item['attributes']['name']=='Refund'), None)
            if not kind:
                raise Problem('The Refund transaction link type is not available in Firefly.', 409)
            kind_id = str(kind['id'])
            journals = [str(s['transaction_journal_id']) for s in current['attributes']['transactions']]
            def links():
                return [item['attributes'] for item in self.client.all('transaction-journals/'+deposit_id+'/links')]
            def refund(link):
                return str(link.get('link_type_id',''))==kind_id or link.get('link_type_name')=='Refund'
            existing = links()
            if any(refund(link) and (str(link['outward_id'])!=deposit_id or str(link['inward_id']) not in journals) for link in existing):
                raise Problem('Deposit already has Refund links to a different withdrawal. Inspect it in Firefly.', 409)
            for withdrawal_id in journals:
                if not any(refund(link) and str(link['inward_id'])==withdrawal_id and str(link['outward_id'])==deposit_id for link in existing):
                    self.client.request('POST','transaction-links',{'link_type_id':kind_id,'inward_id':withdrawal_id,
                                        'outward_id':deposit_id,'notes':'Firefly Sidecar refund match'})
                    existing = links()
                if not any(refund(link) and str(link['inward_id'])==withdrawal_id and str(link['outward_id'])==deposit_id for link in existing):
                    raise Problem('Refund link could not be verified. Todo tag kept; retry this selection.', 502)
        # complete() rechecks the latest tags and uses the same write lock.
        if remove_todo:
            self.complete({'journal_id':deposit_id})
        return {'complete':True,'deposit_id':deposit_id,'group_id':gid,'links':len(journals),'todo_removed':remove_todo}
