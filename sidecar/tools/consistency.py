"""Read-only, bounded checks for the cash conventions used by review tools."""
import os
import threading
import time
import uuid
from datetime import date
from urllib.parse import quote
from ..client import Problem
from .reimbursements import identifier


class Consistency:
    def __init__(self, client, validation):
        self.client,self.validation=client,validation
        self.jobs={};self.jobs_lock=threading.Lock()

    def scan(self, filters, full=False, progress=None):
        try:
            page=int(filters.get('page','1'));limit=int(filters.get('limit','25'))
            if page<1 or page>10000 or limit not in (25,50,100):raise ValueError()
            first=date.fromisoformat(filters.get('start',''));last=date.fromisoformat(filters.get('end',''))
            if first>last:raise ValueError()
        except (ValueError,TypeError):raise Problem('Choose a valid date range and page size.') from None
        rule=filters.get('rule','all');kind=filters.get('type','all')
        if rule not in ('all','gbit','reimbursement','refund') or kind not in ('all','withdrawal','deposit','transfer'):
            raise Problem('Invalid consistency filter.')
        gid=filters.get('group_id','').strip();account=filters.get('account_id','').strip();tag=filters.get('tag','').strip()
        if gid:identifier(gid)
        if account:identifier(account)
        if len(tag)>200:raise Problem('Tag filter is too long.')
        params=dict(start=first.isoformat(),end=last.isoformat(),page=page,limit=limit)
        if kind!='all':params['type']=kind
        if full:params.update(page=1,limit=100)
        candidates={};group_ids=set();fetch_page=params['page'];last_page=fetch_page
        while True:
            if gid:response={'data':[self.client.request('GET','transactions/'+gid)['data']]}
            else:
                path='accounts/'+account+'/transactions' if account else 'tags/'+quote(tag,safe='')+'/transactions' if tag else 'transactions'
                response=self.client.request('GET',path,**dict(params,page=fetch_page))
            groups=response['data']
            pagination=response.get('meta',{}).get('pagination',{})
            last_page=int(pagination.get('total_pages',fetch_page))
            for group in groups:
                group_ids.add(str(group['id']));splits=group['attributes']['transactions']
                for split in splits:
                    when=str(split.get('date',''))[:10]
                    if not first.isoformat()<=when<=last.isoformat():continue
                    if kind!='all' and split.get('type')!=kind:continue
                    if account and account not in (str(split.get('source_id')),str(split.get('destination_id'))):continue
                    if tag and tag not in (split.get('tags') or []):continue
                    jid=str(split['transaction_journal_id'])
                    candidates[jid]=dict(split,journal_id=jid,group_id=str(group['id']),journal_count=len(splits))
            if progress:progress(phase='collecting',pages=fetch_page,total_pages=last_page,total=len(candidates),checked=0,groups=len(group_ids))
            if not full or gid or not groups or fetch_page>=last_page:break
            fetch_page+=1
            if fetch_page>10000:raise Problem('Firefly pagination exceeded the supported limit.',502)
        if not full and len(candidates)>500:raise Problem('This page contains more than 500 journals. Narrow the filters or reduce the page size.')
        cash=self.validation.cash_account()
        reimburse=os.environ.get('REIMBURSE_TAG','Reimburse');gbit_tag=os.environ.get('GBIT_TAG','#GBIT')
        gbit_names={os.environ.get('GBIT_LINK_TYPE','GBIT'),'GBIT','GBIT From'}
        gbit_refund_names={os.environ.get('GBIT_REFUND_LINK_TYPE','GBIT Refund'),'GBIT Refund','GBIT Refunds'}
        reimburse_names={os.environ.get('REIMBURSE_LINK_TYPE','Reimbursement'),'Reimbursement'}
        kinds={str(item['id']):item['attributes']['name'] for item in self.client.all('link-types')}
        findings=[];evaluated=[];errors=[];applicable=0;link_requests=0
        if progress:progress(phase='checking',checked=0,total=len(candidates),groups=len(group_ids))
        for jid,row in candidates.items():
            reasons=[];tags=row.get('tags') or [];kind=row.get('type')
            if rule in ('all','gbit') and gbit_tag in tags:reasons.append('Pending GBIT tag')
            if rule in ('all','reimbursement') and reimburse in tags:reasons.append('Reimbursement tag')
            try:
                link_page=1
                while True:
                    link_requests+=1
                    linked=self.client.request('GET','transaction-journals/'+jid+'/links',limit=100,page=link_page)
                    link_pages=int(linked.get('meta',{}).get('pagination',{}).get('total_pages',1))
                    if not full and link_pages>1:
                        errors.append(dict(group_id=row['group_id'],journal_id=jid,journal_count=row['journal_count'],error='More than one page of links; this journal was not fully checked.'))
                    for item in linked['data']:
                        link=item['attributes'];name=link.get('link_type_name') or kinds.get(str(link.get('link_type_id')),'')
                        if rule in ('all','gbit'):
                            if name in gbit_names and str(link.get('outward_id'))==jid and kind=='withdrawal':reasons.append('GBIT replacement charge')
                            if name in gbit_refund_names and kind=='deposit':reasons.append('GBIT refund deposit')
                        if rule in ('all','reimbursement') and name in reimburse_names and kind=='withdrawal':reasons.append('Linked reimbursement expense')
                        if rule in ('all','refund') and name=='Refund' and kind in ('withdrawal','deposit'):reasons.append('Refund deposit' if kind=='deposit' else 'Refunded expense')
                    if not full or not linked['data'] or link_page>=link_pages:break
                    link_page+=1
                    if link_page>10000:raise Problem('Link pagination exceeded the supported limit.',502)
                    if progress:progress(phase='checking',checked=len(evaluated),total=len(candidates),link_requests=link_requests)
            except Problem as error:
                errors.append(dict(group_id=row['group_id'],journal_id=jid,journal_count=row['journal_count'],error=str(error)))
            if reasons:applicable+=1
            issues=[]
            if reasons and kind not in ('withdrawal','deposit','transfer'):
                issues.append('Unsupported transaction type; inspect manually')
            elif reasons:
                for field,label in (('category','Category'),('budget','Budget'),('bill','Subscription')):
                    if row.get(field+'_id') not in (None,'',0,'0') or row.get(field+'_name') not in (None,''):
                        issues.append(label+' must be cleared')
                field='destination_id' if kind=='withdrawal' else 'source_id' if kind=='deposit' else None
                if field and str(row.get(field))!=cash:issues.append(('Destination' if kind=='withdrawal' else 'Source')+' must be the Cash account #'+cash)
            check_errors=[entry['error'] for entry in errors if entry['journal_id']==jid]
            entry=dict(row,reasons=sorted(set(reasons)),issues=issues,check_errors=check_errors,
                       status='inconsistent' if issues else 'incomplete' if check_errors else 'consistent' if reasons else 'not_applicable')
            evaluated.append(entry)
            if issues:findings.append(entry)
            if progress:progress(phase='checking',checked=len(evaluated),total=len(candidates),inconsistent=len(findings),incomplete=len(errors),link_requests=link_requests)
        pagination=response.get('meta',{}).get('pagination',{})
        next_page=page+1 if not full and not gid and groups and page<int(pagination.get('total_pages',page)) else None
        return dict(findings=findings,evaluated=evaluated,errors=errors,checked=len(candidates),applicable=applicable,
                    groups=len(group_ids),page=page,next_page=next_page,link_requests=link_requests,cash_account_id=cash)


    def start(self, filters):
        filters=dict(filters,limit='100',page='1')
        with self.jobs_lock:
            now=time.monotonic()
            self.jobs={key:job for key,job in self.jobs.items() if job['state']=='running' or now-job['created']<1800}
            if sum(job['state']=='running' for job in self.jobs.values())>=2:
                raise Problem('Two consistency checks are already running. Stop one before starting another.',429)
            completed=[key for key,job in self.jobs.items() if job['state']!='running']
            for key in completed[:-3]:del self.jobs[key]
            job_id=str(uuid.uuid4())
            self.jobs[job_id]={'id':job_id,'created':now,'state':'running','phase':'collecting','checked':0,'total':0,'pages':0,'total_pages':None,'cancel':False}
        def update(**values):
            with self.jobs_lock:
                job=self.jobs[job_id]
                if job['cancel']:raise CancelledScan()
                job.update(values)
        def work():
            try:
                result=self.scan(filters,full=True,progress=update)
                with self.jobs_lock:
                    job=self.jobs[job_id]
                    job.update(state='cancelled' if job['cancel'] else 'complete',result=result)
            except CancelledScan:
                with self.jobs_lock:self.jobs[job_id]['state']='cancelled'
            except Exception as error:
                with self.jobs_lock:self.jobs[job_id].update(state='failed',error=str(error))
        threading.Thread(target=work,daemon=True).start()
        return {'id':job_id}

    def status(self, job_id):
        if not isinstance(job_id,str):raise Problem('Invalid check ID.')
        with self.jobs_lock:
            job=self.jobs.get(job_id)
            if not job:raise Problem('Check not found or expired. Run it again.',404)
            return {key:value for key,value in job.items() if key not in ('created','result','cancel')}

    def cancel(self, job_id):
        if not isinstance(job_id,str):raise Problem('Invalid check ID.')
        with self.jobs_lock:
            job=self.jobs.get(job_id)
            if not job:raise Problem('Check not found or expired.',404)
            job['cancel']=True
        return {'stopping':True}

    def results(self, job_id, page='1', limit='25', show='inconsistent'):
        if not isinstance(job_id,str):raise Problem('Invalid check ID.')
        try:
            page=int(page);limit=int(limit)
            if page<1 or limit not in (25,50,100) or show not in ('all','inconsistent'):raise ValueError()
        except (ValueError,TypeError):raise Problem('Invalid result pagination.') from None
        with self.jobs_lock:
            job=self.jobs.get(job_id)
            if not job:raise Problem('Check not found or expired. Run it again.',404)
            if job['state']!='complete':raise Problem('The check has not completed.',409)
            result=job['result']
            rows=result['evaluated'] if show=='all' else [row for row in result['evaluated'] if row['issues'] or row['check_errors']]
            total=len(rows);pages=max(1,(total+limit-1)//limit);page=min(page,pages)
            return dict(rows=rows[(page-1)*limit:page*limit],total=total,page=page,pages=pages,
                        checked=result['checked'],groups=result['groups'],applicable=result['applicable'],
                        inconsistent=len(result['findings']),incomplete=len(result['errors']))


class CancelledScan(Exception):
    pass
