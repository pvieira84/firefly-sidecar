"""Central audit boundary for all current and future Firefly API writes."""
import copy
import re


def redact(value):
    if isinstance(value, dict):
        return {key: '[redacted]' if any(word in key.lower() for word in ('token', 'password', 'authorization', 'secret')) else redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class AuditedFirefly:
    def __init__(self, client, store):
        self.client, self.store = client, store

    def __getattr__(self, key):
        return getattr(self.client, key)

    def request(self, method, path, body=None, **params):
        action=params.pop('_sidecar_action',None)
        method = method.upper()
        if method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return self.client.request(method, path, body, **params)
        event = {'method': method, 'path': path, 'request': redact(copy.deepcopy(body)),
                 'action': 'Delete transaction' if method == 'DELETE' else 'Create reimbursement link' if path == 'transaction-links' else 'Update transaction' if method in ('PUT', 'PATCH') else 'Create Firefly record',
                 'group_id': None, 'before': None, 'after': None}
        match = re.fullmatch(r'transactions/(\d+)', path)
        if match:
            event['group_id'] = match[1]
        if (path == 'transaction-links' or path.startswith('transaction-links/')) and isinstance(body, dict) and body.get('notes') == 'Firefly Sidecar refund match':
            event['action'] = 'Correct Refund link direction' if method == 'PUT' else 'Create Refund link'
        if path=='transaction-links' and isinstance(body,dict) and str(body.get('notes','')).startswith('Firefly Sidecar GBIT '):
            event['action']='Create GBIT Refund link' if '[GBIT Refund]' in body['notes'] else 'Create GBIT link'
        if action:event['action']=action
        event_id = self.store.start_event(event)  # If this fails, do not mutate Firefly.
        try:
            if match:
                event['before'] = redact(self.client.request('GET', path)['data'])
                if method != 'DELETE' and isinstance(body, dict):
                    patches = {str(p['transaction_journal_id']): p for p in body.get('transactions', []) if 'transaction_journal_id' in p}
                    if not action and any(all(key in patch and patch[key] is None for key in ('category_id', 'budget_id', 'bill_id')) for patch in patches.values()):
                        event['action'] = 'Mark as cash'
                    changes = []
                    for split in event['before']['attributes']['transactions']:
                        patch = patches.get(str(split['transaction_journal_id']), {})
                        if 'tags' in patch:
                            changes.append({'journal_id': str(split['transaction_journal_id']),
                                            'before': split.get('tags') or [], 'after': patch['tags']})
                    if changes and not action:
                        if event['action']!='Mark as cash':event['action'] = 'Update transaction tags'
                        event['tag_changes'] = changes
            elif (path == 'transaction-links' or path.startswith('transaction-links/')) and isinstance(body, dict) and body.get('inward_id'):
                group, _ = self.client.journal(str(body['inward_id']))
                event['group_id'] = str(group['id'])
                event['before'] = redact(copy.deepcopy(group))
            # Persist the snapshot before attempting the remote write.
            self.store.finish_event(event_id, 'pending', event)
        except Exception as error:
            event['error'] = str(error)
            self.store.finish_event(event_id, 'blocked', event)
            raise
        try:
            result = self.client.request(method, path, body, **params)
        except Exception as error:
            event['error'] = str(error)
            # A failed response can follow a successful remote write.
            self.store.finish_event(event_id, 'uncertain', event)
            raise
        event['response'] = redact(result)
        if (path == 'transaction-links' or path.startswith('transaction-links/')) and isinstance(body, dict) and body.get('notes') == 'Firefly Sidecar refund match':
            event['action'] = 'Correct Refund link direction' if method == 'PUT' else 'Create Refund link'
        if path == 'transactions' and isinstance(result, dict) and isinstance(result.get('data'), dict):
            event['group_id'] = str(result['data'].get('id') or '') or None
        if match and method != 'DELETE':
            try:
                event['after'] = redact(self.client.request('GET', path)['data'])
            except Exception as error:
                event['verification_note'] = 'Write accepted, but could not fetch the resulting transaction: ' + str(error)
        self.store.finish_event(event_id, 'completed', event)
        return result


def activity_descriptions(client, page):
    """Enrich legacy link events for display without changing their audit snapshots."""
    from .client import Problem
    parents={}
    for event in page['events']:
        gid=event.get('group_id')
        path=event.get('path') or ''
        if not gid or not (path=='transaction-links' or path.startswith('transaction-links/')):
            continue
        def described(snapshot):
            row=(snapshot or {}).get('attributes',snapshot or {})
            return bool(row.get('group_title') or row.get('description') or
                        any(split.get('description') for split in row.get('transactions',[])))
        if described(event.get('after')) or described(event.get('before')):
            continue
        gid=str(gid)
        if gid not in parents:
            try:parents[gid]=client.request('GET','transactions/'+gid)['data']
            except Problem:parents[gid]=None
        if parents[gid]:event['display_transaction']=parents[gid]
    return page
