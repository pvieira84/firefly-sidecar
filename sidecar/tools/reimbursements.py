import os
import json
import threading
import uuid
from decimal import Decimal, InvalidOperation
from ..client import Problem


def amount(split):
    try:
        value = Decimal(str(split['amount']))
        if not value.is_finite() or value <= 0:
            raise ValueError()
        return value
    except (InvalidOperation, ValueError, KeyError):
        raise Problem('Transaction has an invalid amount.', 409) from None


def identifier(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise Problem('Invalid journal ID.')
    return value


def fingerprint(split):
    # Ignore updated_at and tags for recovery, but detect all financial changes.
    keys = ('transaction_journal_id', 'type', 'date', 'amount', 'currency_id', 'currency_code',
            'foreign_amount', 'foreign_currency_id', 'source_id', 'destination_id',
            'description', 'category_id', 'category_name')
    return {key: split.get(key) for key in keys}


class Reimbursements:
    def __init__(self, client, store):
        self.client, self.store = client, store
        self.tag = os.environ.get('REIMBURSE_TAG', 'Reimburse')
        self.lock = threading.RLock()

    def eligible(self, split):
        return split.get('type') == 'withdrawal' and self.tag in (split.get('tags') or [])

    def row(self, group, split):
        return dict(split, group_id=str(group['id']), group_title=group['attributes'].get('group_title') or '',
                    journal_id=str(split['transaction_journal_id']), journal_count=len(group['attributes']['transactions']))

    def listing(self, start='', end=''):
        deposits, expenses = [], []
        for group in self.client.all('transactions', type='deposit', start=start, end=end):
            deposits.extend(self.row(group, s) for s in group['attributes']['transactions'] if s['type'] == 'deposit')
        # Expense list intentionally independent of deposit date filter: older debts remain visible.
        matches={}
        query='type:withdrawal tag:'+json.dumps(self.tag,ensure_ascii=False)
        for group in self.client.all('search/transactions', query=query):
            for split in group['attributes']['transactions']:
                if self.eligible(split):
                    row=self.row(group,split)
                    matches[row['journal_id']]=row
        expenses=list(matches.values())
        return {'deposits': sorted(deposits, key=lambda s: s['date'], reverse=True),
                'expenses': sorted(expenses, key=lambda s: s['date'], reverse=True),
                'tag': self.tag}

    def link_type(self):
        desired = os.environ.get('REIMBURSE_LINK_TYPE', 'Reimbursement')
        for item in self.client.all('link-types'):
            if item['attributes']['name'] == desired:
                return {'id': str(item['id']), **item['attributes']}
        raise Problem(f'Create or enable the "{desired}" transaction link type in Firefly first.', 409)

    def links(self, journal_id):
        return [dict(x['attributes'], id=str(x['id'])) for x in self.client.all('transaction-journals/' + journal_id + '/links')]

    @staticmethod
    def is_type(link, kind):
        # Firefly versions expose the type as either an ID or name.
        return (str(link.get('link_type_id', '')) == kind['id'] or
                link.get('link_type_name') == kind['name'])

    def matching(self, links, kind, expense, deposit):
        return any(self.is_type(x, kind) and str(x['inward_id']) == deposit and
                   str(x['outward_id']) == expense for x in links)

    def reversed_owned(self, link, plan, expense):
        return (self.is_type(link, plan['link_type']) and
                str(link['inward_id']) == expense and
                str(link['outward_id']) == str(plan['deposit']['transaction_journal_id']) and
                link.get('notes') == 'Firefly Sidecar review ' + plan['id'])

    def prepare(self, body):
        with self.lock:
            deposit_id = identifier(body.get('deposit_id'))
            ids = body.get('expense_ids')
            if not isinstance(ids, list) or not 1 <= len(ids) <= 100:
                raise Problem('Select between 1 and 100 reimbursement splits.')
            ids = [identifier(x) for x in ids]
            if len(set(ids)) != len(ids) or deposit_id in ids:
                raise Problem('Duplicate or invalid selection.')
            deposit_group, deposit_split = self.client.journal(deposit_id)
            deposit = self.row(deposit_group, deposit_split)
            if deposit['type'] != 'deposit':
                raise Problem('Choose a deposit split.', 409)
            kind = self.link_type()
            # Only unallocated deposits are supported in v1. Retry uses the original stored plan.
            if any(self.is_type(x, kind) for x in self.links(deposit_id)):
                raise Problem('This deposit already has reimbursement links. Use History to retry an existing operation, or choose an unallocated deposit.', 409)
            expenses = []
            for jid in ids:
                group, split = self.client.journal(jid)
                if not self.eligible(split):
                    raise Problem(f'Split {jid} is no longer an uncategorized withdrawal tagged {self.tag}. Refresh.', 409)
                if any(self.is_type(x, kind) for x in self.links(jid)):
                    raise Problem(f'Split {jid} already has a reimbursement link. Resolve it in Firefly before matching again.', 409)
                if split['currency_code'] != deposit['currency_code']:
                    raise Problem('All selected splits must use the deposit currency.', 409)
                expenses.append(self.row(group, split))
            total = sum((amount(x) for x in expenses), Decimal(0))
            deposit_amount = amount(deposit)
            plan = {'id': str(uuid.uuid4()), 'deposit': deposit, 'expenses': expenses,
                    'link_type': kind, 'tag': self.tag, 'total': str(total), 'currency': deposit['currency_code'],
                    'difference': str(deposit_amount - total)}
            self.store.save(plan)
            return plan

    def preflight(self, plan):
        deposit_id = str(plan['deposit']['transaction_journal_id'])
        _, deposit = self.client.journal(deposit_id)
        if fingerprint(deposit) != fingerprint(plan['deposit']):
            raise Problem('The deposit changed since review. Refresh and review again.', 409)
        kind = plan['link_type']
        allowed = {x['journal_id'] for x in plan['expenses']}
        for link in self.links(deposit_id):
            if self.is_type(link, kind) and not (
                    (str(link['inward_id']) == deposit_id and str(link['outward_id']) in allowed) or
                    any(self.reversed_owned(link, plan, jid) for jid in allowed)):
                raise Problem('The deposit has acquired a conflicting reimbursement link.', 409)
        for original in plan['expenses']:
            jid = original['journal_id']
            _, current = self.client.journal(jid)
            links = self.links(jid)
            if fingerprint(current) != fingerprint(original):
                raise Problem(f'Split {jid} changed since review. Check Firefly before continuing.', 409)
            if sum(self.is_type(link, kind) for link in links) > 1:
                raise Problem(f'Split {jid} has duplicate reimbursement links. Resolve them in Firefly before continuing.', 409)
            for link in links:
                if self.is_type(link, kind) and not (
                        (str(link['inward_id']) == deposit_id and str(link['outward_id']) == jid) or
                        self.reversed_owned(link, plan, jid)):
                    raise Problem(f'Split {jid} has a conflicting reimbursement link.', 409)
            if plan['tag'] not in (current.get('tags') or []) and not self.matching(links, kind, jid, deposit_id) and not any(self.reversed_owned(link, plan, jid) for link in links):
                raise Problem(f'Split {jid} lost its reimbursement tag without the expected link.', 409)

    def apply(self, plan_id):
        with self.lock:
            plan, state, result = self.store.get(plan_id)
            if state == 'complete' and all(
                    self.matching(self.links(x['journal_id']), plan['link_type'], x['journal_id'],
                                  str(plan['deposit']['transaction_journal_id'])) and
                    not any(self.reversed_owned(link, plan, x['journal_id']) for link in self.links(x['journal_id']))
                    for x in plan['expenses']):
                return result
            self.preflight(plan)  # Validate every selected split before the first write.
            self.store.save(plan, 'applying')
            results = []
            deposit_id = str(plan['deposit']['transaction_journal_id'])
            for original in plan['expenses']:
                jid = original['journal_id']
                try:
                    for link in self.links(jid):
                        if self.reversed_owned(link, plan, jid):
                            self.client.request('PUT', 'transaction-links/' + link['id'], {
                                'link_type_id': plan['link_type']['id'], 'inward_id': deposit_id,
                                'outward_id': jid, 'notes': link['notes']},
                                _sidecar_action='Correct reimbursement link direction')
                    if not self.matching(self.links(jid), plan['link_type'], jid, deposit_id):
                        self.client.request('POST', 'transaction-links', {
                            'link_type_id': plan['link_type']['id'], 'inward_id': deposit_id,
                            'outward_id': jid, 'notes': 'Firefly Sidecar review ' + plan_id})
                    # Verify corrected direction before removing the pending tag.
                    verified_links = self.links(jid)
                    if (not self.matching(verified_links, plan['link_type'], jid, deposit_id) or
                            any(self.reversed_owned(link, plan, jid) for link in verified_links)):
                        raise Problem('Link could not be verified; reimbursement tag was kept.', 502)
                    group, current = self.client.journal(jid)
                    if fingerprint(current) != fingerprint(original):
                        raise Problem('Split changed while applying; link exists, tag was kept.', 409)
                    if plan['tag'] in (current.get('tags') or []):
                        # Include all sibling journal IDs, changing only this split's tag list.
                        updates = []
                        for sibling in group['attributes']['transactions']:
                            patch = {'transaction_journal_id': str(sibling['transaction_journal_id'])}
                            if patch['transaction_journal_id'] == jid:
                                patch['tags'] = [t for t in (sibling.get('tags') or []) if t != plan['tag']]
                            updates.append(patch)
                        payload = {'apply_rules': False, 'fire_webhooks': False, 'transactions': updates}
                        if len(updates) > 1:
                            # Firefly validates this field even for tag-only split updates.
                            payload['group_title'] = group['attributes'].get('group_title')
                        self.client.request('PUT', 'transactions/' + str(group['id']), payload)
                    _, verified = self.client.journal(jid)
                    if plan['tag'] in (verified.get('tags') or []):
                        raise Problem('Link exists but tag removal could not be verified. Retry from History.', 502)
                    if fingerprint(verified) != fingerprint(original):
                        raise Problem('Firefly changed other split fields. Inspect the transaction in Firefly.', 409)
                    results.append({'journal_id': jid, 'status': 'complete'})
                except Problem as e:
                    results.append({'journal_id': jid, 'status': 'failed', 'error': str(e)})
                    # Stop on first failure to make partial outcomes easy to inspect.
                    break
                finally:
                    self.store.save(plan, 'partial', {'items': results})
            complete = len(results) == len(plan['expenses']) and all(x['status'] == 'complete' for x in results)
            result = {'items': results, 'complete': complete, 'plan_id': plan_id}
            self.store.save(plan, 'complete' if complete else 'partial', result)
            return result
