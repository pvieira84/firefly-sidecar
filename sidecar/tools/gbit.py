import os
import uuid
from datetime import date
from urllib.parse import quote
from ..client import Problem
from .duplicates import Duplicates
from .reimbursements import identifier, fingerprint


class GBIT:
    def __init__(self, client, store, validation, lock):
        self.client,self.store,self.validation,self.lock=client,store,validation,lock
        self.tag=os.environ.get('GBIT_TAG','#GBIT')
        if not self.tag.strip() or self.tag==validation.tag:
            raise ValueError('GBIT_TAG must be nonempty and different from TODO_TAG.')

    def group(self, gid):
        return self.client.request('GET','transactions/'+identifier(gid))['data']

    def describe(self, group):
        row,reason=Duplicates.summarize(str(group['id']),group)
        if reason:raise Problem('GBIT requires a supported transaction: '+reason,409)
        return row

    def patch_tags(self, gid, remove, add=None):
        group=self.group(gid)
        patches=[];changed=False
        for split in group['attributes']['transactions']:
            tags=[tag for tag in (split.get('tags') or []) if tag not in remove]
            if add and add not in tags:tags.append(add)
            patch={'transaction_journal_id':str(split['transaction_journal_id'])}
            if tags!=(split.get('tags') or []):patch['tags']=tags;changed=True
            patches.append(patch)
        if not changed:return
        payload={'apply_rules':False,'fire_webhooks':False,'transactions':patches}
        if len(patches)>1:payload['group_title']=group['attributes'].get('group_title')
        self.client.request('PUT','transactions/'+gid,payload)
        after=self.group(gid)
        before_by_id={str(s['transaction_journal_id']):s for s in group['attributes']['transactions']}
        after_by_id={str(s['transaction_journal_id']):s for s in after['attributes']['transactions']}
        if before_by_id.keys()!=after_by_id.keys():raise Problem('Journal set changed during tag update. Inspect Firefly.',409)
        for patch in patches:
            jid=patch['transaction_journal_id'];expected=patch.get('tags',before_by_id[jid].get('tags') or [])
            if (sorted(after_by_id[jid].get('tags') or [])!=sorted(expected) or
                    fingerprint(after_by_id[jid])!=fingerprint(before_by_id[jid])):
                raise Problem('GBIT tag update could not be verified. Retry the saved operation.',409)

    def flag(self, body):
        jid=identifier(body.get('journal_id'))
        with self.lock:
            parent,_=self.client.journal(jid)
            group=self.group(str(parent['id']));row=self.describe(group)
            if row['type'] not in ('withdrawal','deposit'):
                raise Problem('Only withdrawals and deposits can be flagged for GBIT.',409)
            # A transaction flag covers the whole parent, not just the clicked journal.
            self.validation.cash_account()
            for split in group['attributes']['transactions']:
                self.validation.mark_cash({'journal_id':str(split['transaction_journal_id'])})
            self.patch_tags(row['group_id'],{self.validation.tag},self.tag)
            return {'complete':True,'group_id':row['group_id'],'tag':self.tag}

    def listing(self, start, end):
        try:
            first,last=date.fromisoformat(start),date.fromisoformat(end)
            if first>last:raise ValueError()
        except (ValueError,TypeError):raise Problem('Choose a valid original-expense date range.') from None
        ids={str(group['id']) for group in self.client.all('tags/'+quote(self.tag,safe='')+'/transactions')}
        new,refunds,skipped=[],[],[]
        for gid in sorted(ids):
            group=self.group(gid)
            if not any(self.tag in (s.get('tags') or []) for s in group['attributes']['transactions']):continue
            try:row=self.describe(group)
            except Problem as error:skipped.append({'group_id':gid,'reason':str(error)});continue
            if row['type']=='withdrawal':new.append(row)
            elif row['type']=='deposit':refunds.append(row)
        originals={}
        for group in self.client.all('transactions',type='withdrawal',start=start,end=end):
            gid=str(group['id'])
            if gid in ids:continue
            try:row=self.describe(group)
            except Problem:continue
            if row['type']=='withdrawal' and first<=date.fromisoformat(row['date'])<=last:originals[gid]=row
        return {'tag':self.tag,'new_expenses':sorted(new,key=lambda r:r['date'],reverse=True),
                'refunds':sorted(refunds,key=lambda r:r['date'],reverse=True),
                'originals':sorted(originals.values(),key=lambda r:r['date'],reverse=True),
                'skipped':skipped,'operations':self.store.operations('gbit')}

    def prepare(self, body):
        ids={name:identifier(body.get(name)) for name in ('original_id','new_id')}
        if body.get('refund_id'):ids['refund_id']=identifier(body['refund_id'])
        if len(set(ids.values()))!=len(ids):raise Problem('Select different transactions for each role.')
        with self.lock:
            groups={name:self.group(gid) for name,gid in ids.items()}
            rows={name:self.describe(group) for name,group in groups.items()}
            if (rows['original_id']['type']!='withdrawal' or rows['new_id']['type']!='withdrawal' or ('refund_id' in rows and rows['refund_id']['type']!='deposit')):
                raise Problem('Select an original withdrawal, new withdrawal and refund deposit.',409)
            if len({r['currency'] for r in rows.values()})!=1:raise Problem('All three transactions must use the same currency.',409)
            for name in ('new_id','refund_id'):
                if name not in rows:continue
                if self.tag not in rows[name]['tags']:raise Problem('New charge and refund must be flagged GBIT first.',409)
            kinds={item['attributes']['name']:str(item['id']) for item in self.client.all('link-types')}
            if not all(name in kinds for name in ('GBIT','GBIT Refund')):
                raise Problem('Create transaction link types named GBIT and GBIT Refund in Firefly first.',409)
            plan={'id':str(uuid.uuid4()),'kind':'gbit','tag':self.tag,'groups':groups,'rows':rows,
                  'link_types':{name:kinds[name] for name in ('GBIT','GBIT Refund')}}
            original_jids=[str(s['transaction_journal_id']) for s in groups['original_id']['attributes']['transactions']]
            plan['links']=[{'link_type_id':kinds[kind],'inward_id':original,'outward_id':str(split['transaction_journal_id']),
                            'notes':'Firefly Sidecar GBIT '+plan['id']+' ['+kind+']'}
                           for kind,name in (('GBIT','new_id'),('GBIT Refund','refund_id'))
                           if name in groups for original in original_jids for split in groups[name]['attributes']['transactions']]
            if len(plan['links'])>500:raise Problem('Too many journal combinations for one GBIT match.',409)
            self.preflight(plan)
            self.store.save_operation(plan)
            return plan

    def links(self, jid):
        return [item['attributes'] for item in self.client.all('transaction-journals/'+jid+'/links')]

    @staticmethod
    def matches(link, wanted):
        return all(str(link.get(key))==str(wanted[key]) for key in ('link_type_id','inward_id','outward_id'))

    def preflight(self, plan):
        available={item['attributes']['name']:str(item['id']) for item in self.client.all('link-types')}
        if any(available.get(name)!=kind for name,kind in plan['link_types'].items()):
            raise Problem('GBIT link types changed. Reload and review again.',409)
        cash_id=self.validation.cash_account()
        for name,before in plan['groups'].items():
            current=self.group(str(before['id']))
            old={str(s['transaction_journal_id']):s for s in before['attributes']['transactions']}
            now={str(s['transaction_journal_id']):s for s in current['attributes']['transactions']}
            def unchanged(jid):
                original=fingerprint(old[jid]);actual=fingerprint(now[jid])
                if actual==original:return True
                if name=='original_id':return False
                expected=dict(original,category_id=None,category_name=None)
                expected['destination_id' if old[jid]['type']=='withdrawal' else 'source_id']=cash_id
                return actual==expected
            if old.keys()!=now.keys() or any(not unchanged(jid) for jid in old):
                raise Problem('A GBIT transaction changed after review. Reload and review again.',409)
        for original in {link['inward_id'] for link in plan['links']}:
            for existing in self.links(original):
                if str(existing.get('inward_id'))==original and str(existing.get('link_type_id')) in set(plan['link_types'].values()) and not any(self.matches(existing,wanted) for wanted in plan['links']):
                    raise Problem('Original expense has conflicting GBIT links. Inspect it in Firefly.',409)

        for kind,name in (('GBIT','new_id'),('GBIT Refund','refund_id')):
            if name not in plan['groups']:continue
            for split in plan['groups'][name]['attributes']['transactions']:
                jid=str(split['transaction_journal_id'])
                for existing in self.links(jid):
                    if (str(existing.get('outward_id'))==jid and str(existing.get('link_type_id'))==plan['link_types'][kind]
                            and not any(self.matches(existing,wanted) for wanted in plan['links'])):
                        raise Problem('A GBIT participant is already linked to another original expense.',409)

    def apply(self, body):
        operation_id=identifier_uuid(body.get('plan_id'))
        with self.lock:
            plan,state,result=self.store.operation(operation_id,'gbit')
            if state=='complete':return result
            self.preflight(plan)
            self.store.save_operation(plan,'applying')
            try:
                for name in ('new_id','refund_id'):
                    if name not in plan['groups']:continue
                    for split in plan['groups'][name]['attributes']['transactions']:
                        self.validation.mark_cash({'journal_id':str(split['transaction_journal_id'])})
                for wanted in plan['links']:
                    if not any(self.matches(link,wanted) for link in self.links(wanted['inward_id'])):
                        self.client.request('POST','transaction-links',wanted)
                    if not any(self.matches(link,wanted) for link in self.links(wanted['inward_id'])):
                        raise Problem('GBIT link could not be verified; tags have been kept.',502)
                # Recheck the complete set before clearing a single participant's GBIT tag.
                for wanted in plan['links']:
                    if not any(self.matches(link,wanted) for link in self.links(wanted['inward_id'])):
                        raise Problem('GBIT is incomplete; tags have been kept.',409)
                self.preflight(plan)
                if 'refund_id' not in plan['groups']:
                    result={'complete':False,'awaiting_refund':True,'plan_id':operation_id,'links':len(plan['links'])}
                    self.store.save_operation(plan,'awaiting_refund',result)
                    return result
                for group in plan['groups'].values():self.patch_tags(str(group['id']),{plan['tag']})
                result={'complete':True,'plan_id':operation_id,'links':len(plan['links'])}
                self.store.save_operation(plan,'complete',result)
                for operation in self.store.operations('gbit'):
                    old=operation['plan']
                    if operation['state']=='awaiting_refund' and all(str(old['groups'][name]['id'])==str(plan['groups'][name]['id']) for name in ('original_id','new_id')):
                        self.store.save_operation(old,'complete',dict(result,completed_by=operation_id))
                return result
            except Exception as error:
                result={'complete':False,'plan_id':operation_id,'error':str(error)}
                self.store.save_operation(plan,'partial',result)
                return result


def identifier_uuid(value):
    try:return str(uuid.UUID(value))
    except (ValueError,TypeError,AttributeError):raise Problem('Invalid GBIT operation ID.') from None
