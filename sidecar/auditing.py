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
        method = method.upper()
        if method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return self.client.request(method, path, body, **params)
        event = {'method': method, 'path': path, 'request': redact(copy.deepcopy(body)),
                 'action': 'Delete transaction' if method == 'DELETE' else 'Create reimbursement link' if path == 'transaction-links' else 'Update transaction' if method in ('PUT', 'PATCH') else 'Create Firefly record',
                 'group_id': None, 'before': None, 'after': None}
        match = re.fullmatch(r'transactions/(\d+)', path)
        if match:
            event['group_id'] = match[1]
        event_id = self.store.start_event(event)  # If this fails, do not mutate Firefly.
        try:
            if match:
                event['before'] = redact(self.client.request('GET', path)['data'])
                if method != 'DELETE' and isinstance(body, dict):
                    patches = {str(p['transaction_journal_id']): p for p in body.get('transactions', []) if 'transaction_journal_id' in p}
                    changes = []
                    for split in event['before']['attributes']['transactions']:
                        patch = patches.get(str(split['transaction_journal_id']), {})
                        if 'tags' in patch:
                            changes.append({'journal_id': str(split['transaction_journal_id']),
                                            'before': split.get('tags') or [], 'after': patch['tags']})
                    if changes:
                        event['action'] = 'Update transaction tags'
                        event['tag_changes'] = changes
            elif path == 'transaction-links' and isinstance(body, dict) and body.get('inward_id'):
                group, _ = self.client.journal(str(body['inward_id']))
                event['group_id'] = str(group['id'])
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
        if path == 'transactions' and isinstance(result, dict) and isinstance(result.get('data'), dict):
            event['group_id'] = str(result['data'].get('id') or '') or None
        if match and method != 'DELETE':
            try:
                event['after'] = redact(self.client.request('GET', path)['data'])
            except Exception as error:
                event['verification_note'] = 'Write accepted, but could not fetch the resulting transaction: ' + str(error)
        self.store.finish_event(event_id, 'completed', event)
        return result
