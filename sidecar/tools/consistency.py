"""Read-only, bounded checks for the cash conventions used by review tools."""
import os
from datetime import date
from urllib.parse import quote
from ..client import Problem
from .reimbursements import identifier


class Consistency:
    def __init__(self, client, validation):
        self.client,self.validation=client,validation

    def scan(self, filters):
        try:
            page=int(filters.get('page','1'));limit=int(filters.get('limit','25'))
            if page<1 or page>10000 or limit not in (25,50,100):raise ValueError()
            first=date.fromisoformat(filters.get('start',''));last=date.fromisoformat(filters.get('end',''))
            if first>last or (last-first).days>366:raise ValueError()
        except (ValueError,TypeError):raise Problem('Choose a date range of up to 366 days and a valid page size.') from None
        rule=filters.get('rule','all');kind=filters.get('type','all')
        if rule not in ('all','gbit','reimbursement','refund') or kind not in ('all','withdrawal','deposit','transfer'):
            raise Problem('Invalid consistency filter.')
        gid=filters.get('group_id','').strip();account=filters.get('account_id','').strip();tag=filters.get('tag','').strip()
        if gid:identifier(gid)
        if account:identifier(account)
        if len(tag)>200:raise Problem('Tag filter is too long.')
        params=dict(start=first.isoformat(),end=last.isoformat(),page=page,limit=limit)
        if kind!='all':params['type']=kind
        if gid:
            response={'data':[self.client.request('GET','transactions/'+gid)['data']]}
        else:
            path='accounts/'+account+'/transactions' if account else 'tags/'+quote(tag,safe='')+'/transactions' if tag else 'transactions'
            response=self.client.request('GET',path,**params)
        groups=response['data'];candidates={}
        for group in groups:
            splits=group['attributes']['transactions']
            for split in splits:
                when=str(split.get('date',''))[:10]
                if not first.isoformat()<=when<=last.isoformat():continue
                if kind!='all' and split.get('type')!=kind:continue
                if account and account not in (str(split.get('source_id')),str(split.get('destination_id'))):continue
                if tag and tag not in (split.get('tags') or []):continue
                jid=str(split['transaction_journal_id'])
                candidates[jid]=dict(split,journal_id=jid,group_id=str(group['id']),journal_count=len(splits))
        if len(candidates)>500:raise Problem('This page contains more than 500 journals. Narrow the filters or reduce the page size.')
        cash=self.validation.cash_account()
        reimburse=os.environ.get('REIMBURSE_TAG','Reimburse');gbit_tag=os.environ.get('GBIT_TAG','#GBIT')
        gbit_names={os.environ.get('GBIT_LINK_TYPE','GBIT'),'GBIT','GBIT From'}
        gbit_refund_names={os.environ.get('GBIT_REFUND_LINK_TYPE','GBIT Refund'),'GBIT Refund','GBIT Refunds'}
        reimburse_names={os.environ.get('REIMBURSE_LINK_TYPE','Reimbursement'),'Reimbursement'}
        kinds={str(item['id']):item['attributes']['name'] for item in self.client.all('link-types')}
        findings=[];errors=[];applicable=0;link_requests=0
        for jid,row in candidates.items():
            reasons=[];tags=row.get('tags') or [];kind=row.get('type')
            if rule in ('all','gbit') and gbit_tag in tags:reasons.append('Pending GBIT tag')
            if rule in ('all','reimbursement') and reimburse in tags:reasons.append('Reimbursement tag')
            # Links are bounded to one request per journal. Never silently certify
            # a journal when Firefly reports additional link pages.
            try:
                link_requests+=1
                linked=self.client.request('GET','transaction-journals/'+jid+'/links',limit=100,page=1)
                if int(linked.get('meta',{}).get('pagination',{}).get('total_pages',1))>1:
                    errors.append(dict(group_id=row['group_id'],journal_id=jid,journal_count=row['journal_count'],error='More than one page of links; this journal was not fully checked.'))
                for item in linked['data']:
                    link=item['attributes'];name=link.get('link_type_name') or kinds.get(str(link.get('link_type_id')),'')
                    if rule in ('all','gbit'):
                        if name in gbit_names and str(link.get('outward_id'))==jid and kind=='withdrawal':reasons.append('GBIT replacement charge')
                        if name in gbit_refund_names and kind=='deposit':reasons.append('GBIT refund deposit')
                    if rule in ('all','reimbursement') and name in reimburse_names and kind=='withdrawal':reasons.append('Linked reimbursement expense')
                    if rule in ('all','refund') and name=='Refund' and kind in ('withdrawal','deposit'):reasons.append('Refund deposit' if kind=='deposit' else 'Refunded expense')
            except Problem as error:
                errors.append(dict(group_id=row['group_id'],journal_id=jid,journal_count=row['journal_count'],error=str(error)))
            if not reasons:continue
            applicable+=1;issues=[]
            if kind not in ('withdrawal','deposit','transfer'):
                issues.append('Unsupported transaction type; inspect manually')
            else:
                for field,label in (('category','Category'),('budget','Budget'),('bill','Subscription')):
                    if row.get(field+'_id') not in (None,'',0,'0') or row.get(field+'_name') not in (None,''):
                        issues.append(label+' must be cleared')
                field='destination_id' if kind=='withdrawal' else 'source_id' if kind=='deposit' else None
                if field and str(row.get(field))!=cash:issues.append(('Destination' if kind=='withdrawal' else 'Source')+' must be the Cash account #'+cash)
            if issues:findings.append(dict(row,reasons=sorted(set(reasons)),issues=issues))
        pagination=response.get('meta',{}).get('pagination',{})
        next_page=page+1 if not gid and groups and page<int(pagination.get('total_pages',page)) else None
        return dict(findings=findings,errors=errors,checked=len(candidates),applicable=applicable,
                    groups=len(groups),page=page,next_page=next_page,link_requests=link_requests,cash_account_id=cash)
