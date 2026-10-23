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
            for split in group['attributes']['transactions']:
                if self.tag in (split.get('tags') or []):
                    jid = str(split['transaction_journal_id'])
                    rows[jid] = dict(split, journal_id=jid, group_id=str(group['id']),
                                    group_title=group['attributes'].get('group_title') or '', journal_count=len(group['attributes']['transactions']))
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

    def mark_cash(self, body, remove_todo=None):
        if remove_todo is None:remove_todo=self.cash_remove_todo
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
                        not start <= date.fromisoformat(row['date']) <= end or abs(Decimal(row['total'])-total) > tolerance):
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
            journals = [str(s['transaction_journal_id']) for s in current['attributes']['transactions']]
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
        return {'complete':True,'deposit_id':deposit_id,'group_id':gid,'links':len(journals),'todo_removed':remove_todo,'cash_applied':True}

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
        allowed_fields={'source_id','destination_id','category_id','budget_id','bill_id'}
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
            if not expected or all(equal_id(current.get(field),value) and (value is not None or field not in resources or current.get(field.replace('_id','_name')) in (None,'')) for field,value in expected.items()):
                return {'complete':True,'journal_id':jid,'changed':False,'skipped':skipped}
            updates=[]
            for sibling in group['attributes']['transactions']:
                updates.append(patch if str(sibling['transaction_journal_id'])==jid else {'transaction_journal_id':str(sibling['transaction_journal_id'])})
            payload={'apply_rules':False,'fire_webhooks':False,'transactions':updates}
            if len(updates)>1:payload['group_title']=group['attributes'].get('group_title')
            self.client.request('PUT','transactions/'+str(group['id']),payload,_sidecar_action='Categorize transaction')
            _,verified=self.client.journal(jid)
            if any(not equal_id(verified.get(field),value) or (value is None and field in resources and verified.get(field.replace('_id','_name')) not in (None,'')) for field,value in expected.items()):
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
