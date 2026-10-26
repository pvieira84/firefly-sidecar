import os
import copy
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
        self.link_names={'GBIT':os.environ.get('GBIT_LINK_TYPE','GBIT').strip(),
                         'GBIT Refund':os.environ.get('GBIT_REFUND_LINK_TYPE','GBIT Refund').strip()}
        if not all(self.link_names.values()) or len(set(self.link_names.values()))!=2:
            raise ValueError('GBIT_LINK_TYPE and GBIT_REFUND_LINK_TYPE must be nonempty and different.')
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
            if not all(name in kinds for name in self.link_names.values()):
                raise Problem('Create or configure these Firefly link types: '+', '.join(self.link_names.values())+'.',409)
            plan={'id':str(uuid.uuid4()),'kind':'gbit','tag':self.tag,'groups':groups,'rows':rows,
                  'link_types':{key:kinds[name] for key,name in self.link_names.items()},'link_names':dict(self.link_names)}
            available_jids=[str(s['transaction_journal_id']) for s in groups['original_id']['attributes']['transactions']]
            requested=body.get('original_journal_ids')
            if requested is None and 'original_journal_ids' not in body:
                # Keep old API clients and existing saved operations compatible.
                original_jids=available_jids
            else:
                if not isinstance(requested,list) or not requested or len(requested)>500:
                    raise Problem('Select at least one original expense journal.')
                original_jids=[identifier(jid) for jid in requested]
                if len(set(original_jids))!=len(original_jids) or not set(original_jids)<=set(available_jids):
                    raise Problem('Select journals belonging to the original expense.')
            refund_jids=original_jids
            if 'refund_id' in groups and 'refund_original_journal_ids' in body:
                requested=body['refund_original_journal_ids']
                if not isinstance(requested,list) or not requested or len(requested)>500:
                    raise Problem('Select at least one original expense journal for the refund.')
                refund_jids=[identifier(jid) for jid in requested]
                if len(set(refund_jids))!=len(refund_jids) or not set(refund_jids)<=set(available_jids):
                    raise Problem('Refund journals must belong to the original expense.')
            plan['refund_original_journal_ids']=refund_jids if 'refund_id' in groups else []
            plan['original_journal_ids']=original_jids
            selected_group=copy.deepcopy(groups['original_id'])
            selected_group['attributes']['transactions']=[
                split for split in selected_group['attributes']['transactions']
                if str(split['transaction_journal_id']) in original_jids]
            # Keep the full parent snapshot for stale checks; review only the linked journals.
            rows['original_id']=self.describe(selected_group)
            rows['original_id']['journal_count']=len(available_jids)
            if 'refund_id' in groups:
                refund_group=copy.deepcopy(groups['original_id'])
                refund_group['attributes']['transactions']=[split for split in refund_group['attributes']['transactions']
                    if str(split['transaction_journal_id']) in refund_jids]
                plan['refund_original']=self.describe(refund_group)
                plan['refund_original']['journal_count']=len(available_jids)
            plan['links']=[{'link_type_id':plan['link_types'][kind],'inward_id':original if kind=='GBIT' else str(split['transaction_journal_id']),
                            'outward_id':str(split['transaction_journal_id']) if kind=='GBIT' else original,
                            'notes':'Firefly Sidecar GBIT '+plan['id']+' ['+kind+']'}
                           for kind,name in (('GBIT','new_id'),('GBIT Refund','refund_id'))
                           if name in groups for original in (original_jids if kind=='GBIT' else refund_jids) for split in groups[name]['attributes']['transactions']]
            if len(plan['links'])>500:raise Problem('Too many journal combinations for one GBIT match.',409)
            self.preflight(plan)
            # Reopening an identical review should not create another saved attempt.
            for operation in self.store.operations('gbit'):
                old=operation['plan']
                if (operation['state']=='review' and old['groups']==plan['groups']
                        and set(old.get('original_journal_ids',[]))==set(original_jids)
                        and set(old.get('refund_original_journal_ids',old.get('original_journal_ids',[]) if 'refund_id' in old['groups'] else []))==set(plan['refund_original_journal_ids'])
                        and old['link_types']==plan['link_types']
                        and old.get('link_names')==plan['link_names'] and old['tag']==plan['tag']):
                    return old
            self.store.save_operation(plan)
            return plan

    def links(self, jid):
        return [dict(item['attributes'],id=str(item['id'])) for item in self.client.all('transaction-journals/'+jid+'/links')]

    @staticmethod
    def matches(link, wanted):
        return all(str(link.get(key))==str(wanted[key]) for key in ('link_type_id','inward_id','outward_id'))

    def preflight(self, plan):
        available={item['attributes']['name']:str(item['id']) for item in self.client.all('link-types')}
        names=plan.get('link_names',{'GBIT':'GBIT','GBIT Refund':'GBIT Refund'})
        if any(available.get(names[name])!=kind for name,kind in plan['link_types'].items()):
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
        for wanted in plan['links']:
            for jid in (wanted['inward_id'],wanted['outward_id']):
                for existing in self.links(jid):
                    if (str(existing.get('link_type_id'))==str(wanted['link_type_id'])
                            and not any(self.matches(existing,item) or self.owned_reverse(existing,item,plan) for item in plan['links'])):
                        raise Problem('A GBIT participant has conflicting links. Inspect it in Firefly.',409)

    @staticmethod
    def normalize_plan(plan):
        plan=copy.deepcopy(plan)
        refund_ids={str(s['transaction_journal_id']) for s in plan['groups'].get('refund_id',{}).get('attributes',{}).get('transactions',[])}
        for link in plan['links']:
            if str(link['link_type_id'])==str(plan['link_types']['GBIT Refund']) and str(link['outward_id']) in refund_ids:
                link['inward_id'],link['outward_id']=link['outward_id'],link['inward_id']
        return plan

    @staticmethod
    def owned_reverse(link,wanted,plan):
        return (str(wanted['link_type_id'])==str(plan['link_types']['GBIT Refund'])
                and str(link.get('link_type_id'))==str(wanted['link_type_id'])
                and str(link.get('inward_id'))==str(wanted['outward_id'])
                and str(link.get('outward_id'))==str(wanted['inward_id'])
                and str(link.get('notes') or '').startswith('Firefly Sidecar GBIT ')
                and str(link.get('notes') or '').endswith('[GBIT Refund]'))

    def saved(self, operation_id):
        plan,_,result=self.store.operation(identifier_uuid(operation_id),'gbit')
        if result and result.get('completed_by'):
            plan,_,_=self.store.operation(result['completed_by'],'gbit')
        return self.normalize_plan(plan)

    def apply(self, body):
        operation_id=identifier_uuid(body.get('plan_id'))
        with self.lock:
            plan,state,result=self.store.operation(operation_id,'gbit')
            # A completed staged operation points to the later operation with its refund.
            if result and result.get('completed_by'):
                plan,state,result=self.store.operation(result['completed_by'],'gbit')
                operation_id=plan['id']
            plan=self.normalize_plan(plan)
            self.preflight(plan)
            self.store.save_operation(plan,'applying')
            try:
                for name in ('new_id','refund_id'):
                    if name not in plan['groups']:continue
                    for split in plan['groups'][name]['attributes']['transactions']:
                        self.validation.mark_cash({'journal_id':str(split['transaction_journal_id'])})
                for wanted in plan['links']:
                    existing=self.links(wanted['inward_id'])
                    backwards=[link for link in existing if self.owned_reverse(link,wanted,plan)]
                    if len(backwards)>1 or (backwards and any(self.matches(link,wanted) for link in existing)):
                        raise Problem('Multiple GBIT refund links exist for this pair. Inspect Firefly before retrying.',409)
                    if backwards:
                        self.client.request('PUT','transaction-links/'+backwards[0]['id'],wanted)
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
                    if (operation['state']=='awaiting_refund'
                            and {link['inward_id'] for link in old['links'] if str(link['link_type_id'])==str(old['link_types']['GBIT'])}=={link['inward_id'] for link in plan['links'] if str(link['link_type_id'])==str(plan['link_types']['GBIT'])}
                            and all(str(old['groups'][name]['id'])==str(plan['groups'][name]['id']) for name in ('original_id','new_id'))):
                        self.store.save_operation(old,'complete',dict(result,completed_by=operation_id))
                return result
            except Exception as error:
                result={'complete':False,'plan_id':operation_id,'error':str(error)}
                self.store.save_operation(plan,'partial',result)
                return result


def identifier_uuid(value):
    try:return str(uuid.UUID(value))
    except (ValueError,TypeError,AttributeError):raise Problem('Invalid GBIT operation ID.') from None
