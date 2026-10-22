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
            db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, created TEXT, updated TEXT, state TEXT, payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, created TEXT, state TEXT, payload TEXT, result TEXT)')

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

    def events(self, offset=0, limit=50):
        with self.db() as db:
            rows = db.execute('SELECT id, created, updated, state, payload FROM events ORDER BY created DESC, id DESC LIMIT ? OFFSET ?',
                              (limit+1, offset)).fetchall()
        return {'events': [dict(id=r[0], created=r[1], updated=r[2], state=r[3], **json.loads(r[4])) for r in rows[:limit]],
                'next_offset': offset+limit if len(rows)>limit else None}
