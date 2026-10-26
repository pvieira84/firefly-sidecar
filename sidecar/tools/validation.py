import os
import secrets
import time
import copy
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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
        self.reimbursement_previews = {}
        self.categorization_previews = {}
        self.tag = os.environ.get('TODO_TAG', 'todo')
        setting=os.environ.get('MARK_CASH_REMOVE_TODO','true').strip().lower()
        if setting not in ('true','false','1','0','yes','no','on','off'):
            raise ValueError('MARK_CASH_REMOVE_TODO must be true or false.')
        self.cash_remove_todo=setting in ('true','1','yes','on')
        if not self.tag.strip():
            raise ValueError('TODO_TAG must not be empty.')

    def listing(self):
        rows = {}
        for group in self.client.all('tags/' + quote(self.tag, safe='') + '/transactions'):
            totals={}
            for journal in group['attributes']['transactions']:
                currency=journal.get('currency_code') or ''
                totals[currency]=totals.get(currency,Decimal('0'))+Decimal(str(journal['amount']))
            for split in group['attributes']['transactions']:
                if self.tag in (split.get('tags') or []):
                    jid = str(split['transaction_journal_id'])
                    rows[jid] = dict(split, journal_id=jid, group_id=str(group['id']),
                                    group_title=group['attributes'].get('group_title') or group['attributes']['transactions'][0].get('description') or '',
                                    journal_count=len(group['attributes']['transactions']),group_totals={currency:str(amount) for currency,amount in totals.items()})
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

    def complete_group(self, body):
        gid = identifier(body.get('group_id'))
        with self.lock:
            group = self.client.request('GET', 'transactions/' + gid)['data']
            originals = group['attributes']['transactions']
            updates = []
            changed = 0
            for row in originals:
                patch = {'transaction_journal_id': str(row['transaction_journal_id'])}
                if self.tag in (row.get('tags') or []):
                    patch['tags'] = [tag for tag in row['tags'] if tag != self.tag]
                    changed += 1
                updates.append(patch)
            if not changed:
                return {'group_id': gid, 'complete': True, 'validated': 0}
            payload = {'apply_rules': False, 'fire_webhooks': False, 'transactions': updates}
            if len(updates) > 1:
                payload['group_title'] = group['attributes'].get('group_title')
            self.client.request('PUT', 'transactions/' + gid, payload,
                                _sidecar_action='Validate transaction')
            after = self.client.request('GET', 'transactions/' + gid)['data']
            actual = {str(row['transaction_journal_id']): row for row in after['attributes']['transactions']}
            valid = set(actual) == {str(row['transaction_journal_id']) for row in originals}
            for row in originals:
                verified = actual.get(str(row['transaction_journal_id']), {})
                valid = valid and fingerprint(verified) == fingerprint(row)
                valid = valid and sorted(verified.get('tags') or []) == sorted(tag for tag in (row.get('tags') or []) if tag != self.tag)
                valid = valid and all(verified.get(key) == row.get(key) for key in ('budget_id','budget_name','bill_id','bill_name'))
            valid = valid and after['attributes'].get('group_title') == group['attributes'].get('group_title')
            if not valid:
                raise Problem('Transaction validation could not be verified. Inspect Firefly and Activity, then reload the queue before retrying.', 409)
            return {'group_id': gid, 'complete': True, 'validated': changed}

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

    def cash_changes(self, current):
        changes = dict(category_id=None, category_name=None, budget_id=None,
                       budget_name=None, bill_id=None, bill_name=None)
        if current['type'] != 'transfer':
            changes['destination_id' if current['type']=='withdrawal' else 'source_id'] = self.cash_account()
        return changes

    def mark_cash(self, body, remove_todo=None):
        if remove_todo is None:remove_todo=self.cash_remove_todo
        jid = identifier(body.get('journal_id'))
        with self.lock:
            group, current = self.client.journal(jid)
            kind = current.get('type')
            if kind not in ('withdrawal', 'deposit', 'transfer'):
                raise Problem('Mark as cash supports withdrawals, deposits and transfers.', 409)
            changes = self.cash_changes(current)
            expected_tags=[tag for tag in (current.get('tags') or []) if not remove_todo or tag!=self.tag]
            if expected_tags==(current.get('tags') or []) and all((str(current.get(key)) == str(value) if key in ('source_id', 'destination_id') else current.get(key) in (None, '', 0, '0')) for key, value in changes.items()):
                return {'journal_id': jid, 'complete': True}
            updates = []
            for sibling in group['attributes']['transactions']:
                patch = {'transaction_journal_id': str(sibling['transaction_journal_id'])}
                if patch['transaction_journal_id'] == jid:
                    patch.update(changes)
                    if expected_tags!=(current.get('tags') or []):patch['tags']=expected_tags
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
                    sorted(verified.get('tags') or []) != sorted(expected_tags)):
                raise Problem('Firefly changed other transaction fields. Inspect the transaction before retrying.', 409)
            return {'journal_id': jid, 'complete': True}

    def reimbursement_options(self, body):
        jid = identifier(body.get('journal_id'))
        with self.lock:
            group, row = self.client.journal(jid)
            if row.get('type') not in ('withdrawal', 'deposit', 'transfer'):
                raise Problem('This transaction type cannot be split.', 409)
            now = time.monotonic()
            self.reimbursement_previews = {k:v for k,v in self.reimbursement_previews.items() if now-v['created'] < 600}
            if len(self.reimbursement_previews) >= 100:
                raise Problem('Too many split previews. Close old previews and retry later.', 429)
            token = secrets.token_urlsafe(32)
            self.reimbursement_previews[token] = dict(created=now, group=copy.deepcopy(group), journal_id=jid)
            return dict(token=token, transaction=dict(row, group_id=str(group['id']), journal_count=len(group['attributes']['transactions'])))

    def mark_reimbursement(self, body):
        return self.split_transaction(dict(body, reimbursement=True))

    def split_transaction(self, body):
        reimbursement=body.get('reimbursement',False)
        if not isinstance(reimbursement,bool):raise Problem('Invalid reimbursement option.')
        with self.lock:
            token = body.get('token')
            preview = self.reimbursement_previews.get(token) if isinstance(token, str) else None
            if not preview or time.monotonic()-preview['created'] >= 600:
                raise Problem('Open a new split preview before applying.', 409)
            group, current = self.client.journal(preview['journal_id'])
            if group != preview['group']:
                raise Problem('Transaction changed. Close this dialog and review it again.', 409)
            try:
                total = Decimal(str(current['amount']))
                precision = int(current.get('currency_decimal_places', 2))
                if not 0 <= precision <= 12: raise ValueError()
                quantum = Decimal(1).scaleb(-precision)
                value = Decimal(str(body.get('value')))
                mode = body.get('mode')
                if not total.is_finite() or total <= 0 or not value.is_finite() or value <= 0:
                    raise ValueError()
                if mode == 'percent' and value <= 100:
                    amount = (total * value / 100).quantize(quantum, rounding=ROUND_HALF_UP)
                elif mode == 'amount' and value <= total and value == value.quantize(quantum):
                    amount = value
                else: raise ValueError()
                if amount <= 0 or amount > total or total != total.quantize(quantum): raise ValueError()
            except (InvalidOperation, ValueError, TypeError, OverflowError):
                raise Problem('Enter a positive percentage up to 100, or an amount up to the original total using the currency precision.') from None
            partial = amount != total
            if not partial and not reimbursement:raise Problem('A regular split must leave a positive remaining amount.')
            description='Reimbursement' if reimbursement else body.get('description',current['description'])
            if not isinstance(description,str) or not description.strip() or len(description)>1000:
                raise Problem('Enter a new split description between 1 and 1000 characters.')
            changes = self.cash_changes(current) if reimbursement else {}
            tags = [t for t in (current.get('tags') or []) if not reimbursement or t != self.tag]
            changes['tags'] = list(dict.fromkeys(tags + ([os.environ.get('REIMBURSE_TAG','Reimburse')] if reimbursement else [])))
            updates = []
            for sibling in group['attributes']['transactions']:
                patch = {'transaction_journal_id':str(sibling['transaction_journal_id']),
                         'tags':[t for t in (sibling.get('tags') or []) if not reimbursement or t != self.tag]}
                if patch['transaction_journal_id'] == preview['journal_id']:
                    patch.update({'amount':str(total-amount)} if partial else changes)
                updates.append(patch)
            if partial:
                # Copy only writable journal fields; never copy imported IDs to a new split.
                fields = ('type','date','source_id','destination_id','currency_id','foreign_currency_id',
                          'notes','category_id','category_name','budget_id','budget_name','bill_id','bill_name','tags','interest_date','book_date',
                          'process_date','due_date','payment_date','invoice_date','sepa_cc','sepa_ct_op',
                          'sepa_ct_id','sepa_db','sepa_country','sepa_ep','sepa_ci','sepa_batch_id')
                new = {key:copy.deepcopy(current[key]) for key in fields if current.get(key) is not None}
                new.update(changes, description=description, amount=str(amount))
                if current.get('foreign_amount') not in (None, ''):
                    try:
                        foreign = Decimal(str(current['foreign_amount']))
                        places = int(current.get('foreign_currency_decimal_places', 2))
                        if not foreign.is_finite() or foreign <= 0 or not 0 <= places <= 12: raise ValueError()
                        foreign_part = (foreign*amount/total).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
                        if not 0 < foreign_part < foreign: raise ValueError()
                    except (InvalidOperation, ValueError, TypeError):
                        raise Problem('This foreign currency amount cannot be split at its currency precision.') from None
                    new['foreign_amount'] = str(foreign_part)
                    next(p for p in updates if p['transaction_journal_id']==preview['journal_id'])['foreign_amount'] = str(foreign-foreign_part)
                updates.append(new)
            title = group['attributes'].get('group_title') or current['description']
            payload = dict(apply_rules=False, fire_webhooks=False, transactions=updates)
            if len(updates)>1: payload['group_title'] = title
            # Consume before sending: an uncertain write must be inspected, never replayed.
            del self.reimbursement_previews[token]
            self.client.request('PUT', 'transactions/'+str(group['id']), payload,
                                _sidecar_action='Mark as reimbursement' if reimbursement else 'Split transaction')
            after = self.client.request('GET', 'transactions/'+str(group['id']))['data']
            before_rows = group['attributes']['transactions']
            after_rows = after['attributes']['transactions']
            old_ids = {str(r['transaction_journal_id']) for r in before_rows}
            new_rows = [r for r in after_rows if str(r['transaction_journal_id']) not in old_ids]
            by_id = {str(r['transaction_journal_id']):r for r in after_rows}
            target = new_rows[0] if partial and len(new_rows)==1 else by_id.get(preview['journal_id'], {})
            valid = len(after_rows)==len(before_rows)+int(partial)
            valid = valid and Decimal(str(target.get('amount', 0)))==amount
            valid = valid and target.get('description')==(description if partial else current['description'])
            expected_target = dict(current, **changes)
            if partial: expected_target['amount'] = str(amount)
            if partial: expected_target.update(description=description, transaction_journal_id=target.get('transaction_journal_id'))
            if partial and current.get('foreign_amount') not in (None, ''):
                expected_target['foreign_amount'] = str(foreign_part)
            def same_finances(actual, expected):
                left, right = fingerprint(actual), fingerprint(expected)
                for key in ('amount', 'foreign_amount'):
                    if left.get(key) not in (None, '') and right.get(key) not in (None, ''):
                        left[key], right[key] = Decimal(str(left[key])), Decimal(str(right[key]))
                return left == right
            valid = valid and same_finances(target, expected_target)
            valid = valid and sorted(target.get('tags') or [])==sorted(changes['tags'])
            valid = valid and all((str(target.get(k))==str(v) if k in ('source_id','destination_id') else target.get(k) in (None,'',0,'0')) for k,v in changes.items() if k!='tags')
            for original in before_rows:
                actual = by_id.get(str(original['transaction_journal_id']), {})
                if str(original['transaction_journal_id']) != preview['journal_id'] or partial:
                    expected = copy.deepcopy(original)
                    expected['tags'] = [t for t in (original.get('tags') or []) if not reimbursement or t != self.tag]
                    if str(original['transaction_journal_id']) == preview['journal_id']:
                        expected.update(next(p for p in updates if p.get('transaction_journal_id')==preview['journal_id']))
                    valid = valid and same_finances(actual, expected) and sorted(actual.get('tags') or [])==sorted(expected.get('tags') or [])
            valid = valid and sum(Decimal(str(r['amount'])) for r in before_rows)==sum(Decimal(str(r['amount'])) for r in after_rows)
            if len(updates)>1: valid = valid and after['attributes'].get('group_title')==title
            if not valid:
                raise Problem('Split verification failed. Inspect the transaction and Activity before making further changes.', 409)
            return dict(complete=True, group_id=str(group['id']), amount=str(amount), remaining=str(total-amount), partial=partial)

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
            same_account = body.get('same_account', True)
            if not isinstance(same_account, bool):
                raise Problem('Same-account setting must be a checkbox value.')
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
                        not start <= date.fromisoformat(row['date']) <= end or
                        (abs(Decimal(row['total'])-total) > tolerance and
                         (len(row['splits'])==1 or Decimal(row['total'])+tolerance<total))):
                    continue
                if same_account and any(str(s.get('source_id')) != str(deposit.get('destination_id')) for s in group['attributes']['transactions']):
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
            self.refund_previews[token] = {'created': now, 'deposit': copy.deepcopy(deposit), 'candidates': snapshots, 'same_account': same_account}
            return {'token': token, 'deposit': dict(deposit, group_id=str(parent['id'])), 'candidates': candidates,
                    'start': start.isoformat(), 'end': end.isoformat(), 'tolerance': str(tolerance), 'skipped': skipped, 'same_account': same_account}

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
            cash_id = self.cash_account()  # Resolve before creating any links.
            def original_or_cash(actual, before):
                original_values = fingerprint(before)
                cash_values = dict(original_values, category_id=None, category_name=None)
                cash_values['source_id' if before['type']=='deposit' else 'destination_id'] = cash_id
                return fingerprint(actual) in (original_values, cash_values)
            before_splits = {str(s['transaction_journal_id']):s for s in original['attributes']['transactions']}
            now_splits = {str(s['transaction_journal_id']):s for s in current['attributes']['transactions']}
            if (not original_or_cash(current_deposit, deposit) or before_splits.keys()!=now_splits.keys() or
                    any(not original_or_cash(now_splits[jid], before_splits[jid]) for jid in before_splits)):
                raise Problem('Deposit or withdrawal changed since search. Load withdrawals again.', 409)
            kind = next((item for item in self.client.all('link-types') if item['attributes']['name']=='Refund'), None)
            if not kind:
                raise Problem('The Refund transaction link type is not available in Firefly.', 409)
            kind_id = str(kind['id'])
            available = [str(s['transaction_journal_id']) for s in current['attributes']['transactions']]
            requested = body.get('journal_ids', available)
            if not isinstance(requested,list) or not requested or len(requested)>500:
                raise Problem('Select at least one withdrawal split to refund.')
            journals = [identifier(jid) for jid in requested]
            if len(set(journals))!=len(journals) or not set(journals)<=set(available):
                raise Problem('Select splits belonging to the chosen withdrawal.')
            def links():
                return [dict(item['attributes'], id=str(item['id'])) for item in self.client.all('transaction-journals/'+deposit_id+'/links')]
            def refund(link):
                return str(link.get('link_type_id',''))==kind_id or link.get('link_type_name')=='Refund'
            existing = links()
            def correct(link, withdrawal_id):
                return refund(link) and str(link['inward_id'])==deposit_id and str(link['outward_id'])==withdrawal_id
            def reversed_owned(link, withdrawal_id):
                return (refund(link) and str(link['inward_id'])==withdrawal_id and str(link['outward_id'])==deposit_id
                        and link.get('notes')=='Firefly Sidecar refund match')
            if any(refund(link) and not any(correct(link,jid) or reversed_owned(link,jid) for jid in journals) for link in existing):
                raise Problem('Deposit has conflicting Refund links. Inspect it in Firefly.', 409)
            for withdrawal_id in journals:
                backwards = [link for link in existing if reversed_owned(link,withdrawal_id)]
                if len(backwards)>1 or (backwards and any(correct(link,withdrawal_id) for link in existing)):
                    raise Problem('Multiple Refund links exist for this pair. Inspect them in Firefly before retrying.',409)
            for withdrawal_id in journals:
                backwards = next((link for link in existing if reversed_owned(link,withdrawal_id)), None)
                payload={'link_type_id':kind_id,'inward_id':deposit_id,'outward_id':withdrawal_id,
                         'notes':'Firefly Sidecar refund match'}
                if backwards:
                    self.client.request('PUT','transaction-links/'+backwards['id'],payload)
                    existing=links()
                elif not any(correct(link,withdrawal_id) for link in existing):
                    self.client.request('POST','transaction-links',payload)
                    existing=links()
                if not any(correct(link,withdrawal_id) for link in existing):
                    raise Problem('Refund link could not be verified. Todo tag kept; retry this selection.',502)
        # Each step is audited independently; retries accept already-applied cash changes.
        for withdrawal_id in journals:
            self.mark_cash({'journal_id':withdrawal_id},remove_todo=False)
        self.mark_cash({'journal_id':deposit_id},remove_todo=False)
        if remove_todo:
            self.complete({'journal_id':deposit_id})
        return {'complete':True,'deposit_id':deposit_id,'group_id':gid,'links':len(journals),'todo_removed':remove_todo,'cash_applied':True,'journal_ids':journals}

    @staticmethod
    def account_type(value):
        return {'Asset account':'asset','Cash account':'cash','Expense account':'expense',
                'Revenue account':'revenue','Loan':'liability','Debt':'liability','Mortgage':'liability'}.get(value,value)

    @staticmethod
    def allowed_account_types(kind, field):
        return {('withdrawal','source_id'):{'asset','liability'},('withdrawal','destination_id'):{'expense','cash'},
                ('deposit','source_id'):{'revenue','cash'},('deposit','destination_id'):{'asset','liability'},
                ('transfer','source_id'):{'asset','liability'},('transfer','destination_id'):{'asset','liability'}}.get((kind,field),set())

    @staticmethod
    def categorization_fingerprint(row):
        return dict(fingerprint(row),budget_id=row.get('budget_id'),bill_id=row.get('bill_id'),
                    tags=sorted(row.get('tags') or []))

    def categorize_options(self, body):
        ids=body.get('journal_ids')
        if not isinstance(ids,list) or not 1<=len(ids)<=200:
            raise Problem('Select between 1 and 200 journals to categorize.')
        ids=list(dict.fromkeys(identifier(jid) for jid in ids))
        with self.lock:
            cache={};targets={}
            for jid in ids:
                if jid not in cache:
                    group,_=self.client.journal(jid)
                    for row in group['attributes']['transactions']:
                        cache[str(row['transaction_journal_id'])]=dict(row,group_id=str(group['id']),journal_count=len(group['attributes']['transactions']))
                row=cache[jid]
                if row.get('type') not in ('withdrawal','deposit','transfer'):
                    raise Problem('Categorization supports withdrawals, deposits and transfers.',409)
                targets[jid]=copy.deepcopy(row)
            options={}
            for endpoint in ('accounts','categories','budgets','bills'):
                entries=self.client.all(endpoint,**({'type':'all'} if endpoint=='accounts' else {}))
                options[endpoint]=sorted([{'id':str(item['id']),'name':item['attributes'].get('name') or str(item['id']),
                                           'type':self.account_type(item['attributes'].get('type'))}
                                          for item in entries if item['attributes'].get('active') is not False],key=lambda item:item['name'].casefold())
            now=time.monotonic()
            self.categorization_previews={k:v for k,v in self.categorization_previews.items() if now-v['created']<600}
            if len(self.categorization_previews)>=50:raise Problem('Too many categorization dialogs. Retry later.',429)
            token=secrets.token_urlsafe(32)
            self.categorization_previews[token]={'created':now,'targets':targets,'options':options}
            rows=[]
            for jid,row in targets.items():
                allowed={field:[account['id'] for account in options['accounts'] if account['type'] in self.allowed_account_types(row['type'],field)] for field in ('source_id','destination_id')}
                rows.append(dict(row,journal_id=jid,allowed_accounts=allowed))
            return dict(options,token=token,transactions=rows)

    def categorize(self, body):
        jid=identifier(body.get('journal_id'));token=body.get('token');changes=body.get('changes')
        allowed_fields={'source_id','destination_id','category_id','budget_id','bill_id','description'}
        if not isinstance(token,str) or len(token)>100 or not isinstance(changes,dict) or not changes or set(changes)-allowed_fields:
            raise Problem('Choose at least one valid categorization change.')
        with self.lock:
            preview=self.categorization_previews.get(token)
            if not preview or time.monotonic()-preview['created']>=600 or jid not in preview['targets']:
                raise Problem('Categorization dialog expired. Reopen it before applying changes.',409)
            group,current=self.client.journal(jid)
            if self.categorization_fingerprint(current)!=self.categorization_fingerprint(preview['targets'][jid]):
                raise Problem('Transaction changed since the dialog opened. Reload and review again.',409)
            kind=current['type'];patch={'transaction_journal_id':jid};expected={};skipped=[]
            resources={'category_id':'categories','budget_id':'budgets','bill_id':'bills'}
            for field,value in changes.items():
                if field in ('budget_id','bill_id') and kind!='withdrawal':
                    skipped.append(field);continue
                if field == 'description':
                    if not isinstance(value,str) or not value.strip() or len(value)>1000:
                        raise Problem('Description must contain between 1 and 1000 characters.')
                    patch[field]=value;expected[field]=value
                    continue
                if value is not None:identifier(value)
                if field in ('source_id','destination_id'):
                    if value is None:raise Problem('Accounts cannot be cleared.')
                    accounts={account['id']:account for account in preview['options']['accounts']}
                    if value not in accounts or accounts[value]['type'] not in self.allowed_account_types(kind,field):
                        raise Problem('Selected account is not valid for this transaction type.',409)
                elif value is not None and value not in {item['id'] for item in preview['options'][resources[field]]}:
                    raise Problem('Selected category, budget or subscription is unavailable.',409)
                patch[field]=value;expected[field]=value
                if field in resources and value is None:patch[field.replace('_id','_name')]=None
            if str(patch.get('source_id',current.get('source_id')))==str(patch.get('destination_id',current.get('destination_id'))):
                raise Problem('Source and destination accounts must differ.',409)
            def equal_id(left,right):return (None if left in (None,'',0,'0') else str(left))==(None if right in (None,'',0,'0') else str(right))
            def equal_field(field,left,right):return left==right if field=='description' else equal_id(left,right)
            if not expected or all(equal_field(field,current.get(field),value) and (value is not None or field not in resources or current.get(field.replace('_id','_name')) in (None,'')) for field,value in expected.items()):
                return {'complete':True,'journal_id':jid,'changed':False,'skipped':skipped}
            updates=[]
            for sibling in group['attributes']['transactions']:
                updates.append(patch if str(sibling['transaction_journal_id'])==jid else {'transaction_journal_id':str(sibling['transaction_journal_id'])})
            payload={'apply_rules':False,'fire_webhooks':False,'transactions':updates}
            if len(updates)>1:payload['group_title']=group['attributes'].get('group_title')
            self.client.request('PUT','transactions/'+str(group['id']),payload,_sidecar_action='Categorize transaction')
            _,verified=self.client.journal(jid)
            if any(not equal_field(field,verified.get(field),value) or (value is None and field in resources and verified.get(field.replace('_id','_name')) not in (None,'')) for field,value in expected.items()):
                raise Problem('Categorization update could not be verified. Inspect Firefly before retrying.',409)
            before=fingerprint(current);after=fingerprint(verified)
            ignore=set(expected)|({'category_name'} if 'category_id' in expected else set())
            if any(before[key]!=after[key] for key in before if key not in ignore) or sorted(current.get('tags') or [])!=sorted(verified.get('tags') or []):
                raise Problem('Firefly changed other transaction fields. Inspect before retrying.',409)
            for key in ('budget_id','bill_id'):
                if key not in expected and not equal_id(current.get(key),verified.get(key)):
                    raise Problem('Firefly changed an unselected assignment. Inspect before retrying.',409)
            preview['targets'][jid]=copy.deepcopy(verified)
            return {'complete':True,'journal_id':jid,'changed':True,'skipped':skipped}
