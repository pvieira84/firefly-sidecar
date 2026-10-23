import json
import uuid
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


class Store:
    def __init__(self, filename):
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        self.filename = filename
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, kind TEXT, created TEXT, state TEXT, payload TEXT, result TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, created TEXT, updated TEXT, state TEXT, payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, created TEXT, state TEXT, payload TEXT, result TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS events_created_idx ON events(created DESC, id DESC)')
            db.execute('CREATE INDEX IF NOT EXISTS events_state_idx ON events(state, created DESC)')
            db.execute("CREATE INDEX IF NOT EXISTS events_action_idx ON events(json_extract(payload, '$.action'), created DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS events_group_idx ON events(CAST(json_extract(payload, '$.group_id') AS TEXT), created DESC)")

    def db(self):
        return sqlite3.connect(self.filename, timeout=30)

    def save(self, plan, state='review', result=None):
        with self.db() as db:
            db.execute('INSERT INTO plans VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET state=excluded.state, result=excluded.result',
                       (plan['id'], datetime.now(timezone.utc).isoformat(), state, json.dumps(plan), json.dumps(result)))

    def get(self, plan_id):
        with self.db() as db:
            row = db.execute('SELECT payload, state, result FROM plans WHERE id=?', (plan_id,)).fetchone()
        if not row:
            from .client import Problem
            raise Problem('Review not found. Create a new review.', 404)
        return json.loads(row[0]), row[1], json.loads(row[2])

    def history(self):
        with self.db() as db:
            rows = db.execute('SELECT id, created, state, payload, result FROM plans ORDER BY created DESC LIMIT 50').fetchall()
        return [{'id': r[0], 'created': r[1], 'state': r[2], 'plan': json.loads(r[3]), 'result': json.loads(r[4])} for r in rows]

    def start_event(self, event):
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.db() as db:
            db.execute('INSERT INTO events VALUES (?, ?, ?, ?, ?)',
                       (event_id, now, now, 'pending', json.dumps(event)))
        return event_id

    def finish_event(self, event_id, state, event):
        with self.db() as db:
            db.execute('UPDATE events SET updated=?, state=?, payload=? WHERE id=?',
                       (datetime.now(timezone.utc).isoformat(), state, json.dumps(event), event_id))

    def events(self, offset=0, limit=50, state='', action='', group_id='', start='', end=''):
        timeline = """WITH timeline AS (
            SELECT id,created,updated,state,payload FROM events
            UNION ALL
            SELECT 'reimbursement:' || id,created,created,
                   CASE state WHEN 'complete' THEN 'completed' WHEN 'applying' THEN 'pending' ELSE state END,
                   json_object('action','Reimbursement','entry_type','reimbursement','plan_id',id,
                               'group_id',json_extract(payload,'$.deposit.group_id'),
                               'plan',json(payload),'result',json(COALESCE(result,'null')),'operation_state',state)
            FROM plans
        ) """
        conditions=[];params=[]
        for expression,value in (("state",state),("json_extract(payload, '$.action')",action)):
            if value:
                conditions.append(expression+' = ?');params.append(value)
        if group_id:
            conditions.append("(CAST(json_extract(payload, '$.group_id') AS TEXT) = ? OR EXISTS (SELECT 1 FROM json_each(payload, '$.plan.expenses') AS expense WHERE CAST(json_extract(expense.value, '$.group_id') AS TEXT) = ?))")
            params.extend([group_id,group_id])
        if start:conditions.append('created >= ?');params.append(start+'T00:00:00')
        if end:
            from datetime import date, timedelta
            conditions.append('created < ?');params.append((date.fromisoformat(end)+timedelta(days=1)).isoformat()+'T00:00:00')
        where=' WHERE '+' AND '.join(conditions) if conditions else ''
        with self.db() as db:
            total=db.execute(timeline+'SELECT COUNT(*) FROM timeline'+where,params).fetchone()[0]
            offset=min(offset,((total-1)//limit)*limit) if total else 0
            rows=db.execute(timeline+'SELECT id, created, updated, state, payload FROM timeline'+where+
                            ' ORDER BY created DESC, id DESC LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
            actions=[row[0] for row in db.execute(timeline+"SELECT DISTINCT json_extract(payload, '$.action') FROM timeline ORDER BY 1") if row[0]]
        return {'events':[dict(id=r[0],created=r[1],updated=r[2],state=r[3],**json.loads(r[4])) for r in rows],
                'total':total,'offset':offset,'limit':limit,'actions':actions,
                'previous_offset':max(0,offset-limit) if offset else None,
                'next_offset':offset+limit if offset+limit<total else None}

    def save_operation(self, plan, state='review', result=None):
        with self.db() as db:
            db.execute('INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,result=excluded.result',
                       (plan['id'], plan['kind'], datetime.now(timezone.utc).isoformat(), state, json.dumps(plan), json.dumps(result)))

    def operation(self, operation_id, kind):
        with self.db() as db:
            row=db.execute('SELECT payload,state,result FROM operations WHERE id=? AND kind=?',(operation_id,kind)).fetchone()
        if not row:
            from .client import Problem
            raise Problem('Operation not found.',404)
        return json.loads(row[0]),row[1],json.loads(row[2])

    def operations(self, kind):
        with self.db() as db:
            rows=db.execute('SELECT payload,state,result,created FROM operations WHERE kind=? ORDER BY created DESC LIMIT 100',(kind,)).fetchall()
        return [{'plan':json.loads(r[0]),'state':r[1],'result':json.loads(r[2]),'created':r[3]} for r in rows]
