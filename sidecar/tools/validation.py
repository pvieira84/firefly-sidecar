import os
import secrets
import time
import copy
from urllib.parse import quote
from ..client import Problem
from .reimbursements import identifier, fingerprint
from .duplicates import Duplicates


class Validation:
    """Review queue; actions operate on individual journals, including unsplit transactions."""
    def __init__(self, client, lock):
        self.client, self.lock = client, lock
        self.deletion_previews = {}
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
