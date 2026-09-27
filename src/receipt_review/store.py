"""SQLite 持久化：原始预测不可覆盖，复核用事务和版本号防丢失更新。"""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from receipt_review.normalize import money, receipt_date
from receipt_review.schemas import FIELD_NAMES


class Conflict(Exception):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL,
                    image_name TEXT NOT NULL, prediction TEXT NOT NULL,
                    current_fields TEXT NOT NULL, status TEXT NOT NULL,
                    revision INTEGER NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY, document_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, fields TEXT NOT NULL,
                    status TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(document_id, revision));
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def add(self, digest, image_name, prediction):
        fields = {name: prediction.get('fields', {}).get(name, {}).get('value') for name in FIELD_NAMES}
        with closing(self.connect()) as db, db:
            identity = uuid4().hex
            cursor = db.execute('INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?,?,?,?)', (
                identity, digest, image_name, json.dumps(prediction, ensure_ascii=False),
                json.dumps(fields, ensure_ascii=False), 'pending', 1, self.now()))
            duplicate = cursor.rowcount == 0
            row = db.execute('SELECT id FROM documents WHERE sha256=?', (digest,)).fetchone()
        return self.get(row['id']), duplicate

    def by_digest(self, digest):
        with closing(self.connect()) as db:
            row = db.execute('SELECT id FROM documents WHERE sha256=?', (digest,)).fetchone()
        return self.get(row['id']) if row else None

    def get(self, identity):
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM documents WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise KeyError(identity)
            data = dict(row)
            data['prediction'] = json.loads(data['prediction'])
            data['current_fields'] = json.loads(data['current_fields'])
            data['history'] = [dict(x) for x in db.execute('SELECT revision,fields,status,note,created_at FROM history WHERE document_id=? ORDER BY revision', (identity,))]
            for event in data['history']:
                event['fields'] = json.loads(event['fields'])
        return data

    def list(self):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute('SELECT id,status,revision,created_at FROM documents ORDER BY created_at DESC LIMIT 100')]

    def review(self, identity, revision, fields, status, note):
        if status not in {'confirmed', 'rejected'} or type(revision) is not int or revision < 1:
            raise ValueError('复核状态或版本非法')
        if not isinstance(note, str) or not note.strip() or len(note) > 1000:
            raise ValueError('请填写不超过 1000 字的复核说明')
        if set(fields) - set(FIELD_NAMES):
            raise ValueError('未知字段')
        clean = {}
        for name in FIELD_NAMES:
            value = fields.get(name)
            if value is not None and (not isinstance(value, str) or len(value) > 1000):
                raise ValueError('字段须为不超过 1000 字的文本')
            clean[name] = value.strip() if value and value.strip() else None
        if status == 'confirmed':
            if not all(clean.values()):
                raise ValueError('确认前必须填全四个字段')
            clean['total'] = money(clean['total'])
            clean['date'], ambiguous = receipt_date(clean['date'])
            if ambiguous:
                raise ValueError('日期有歧义，请按 YYYY-MM-DD 填写')
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            exists = db.execute('SELECT revision FROM documents WHERE id=?', (identity,)).fetchone()
            if exists is None:
                raise KeyError(identity)
            if exists['revision'] != revision:
                raise Conflict('记录已被更新，请刷新后重新复核')
            dumped = json.dumps(clean, ensure_ascii=False)
            db.execute('UPDATE documents SET current_fields=?,status=?,revision=revision+1 WHERE id=?', (dumped, status, identity))
            db.execute('INSERT INTO history(document_id,revision,fields,status,note,created_at) VALUES(?,?,?,?,?,?)', (identity, revision + 1, dumped, status, note.strip(), self.now()))
        return self.get(identity)

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()
