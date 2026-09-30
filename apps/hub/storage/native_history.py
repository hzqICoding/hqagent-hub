"""Rebuildable native metadata/offset cache. Never stores message bodies."""
import json


class NativeHistoryRepository:
    def __init__(self, database):
        self.database = database

    def load(self, key):
        with self.database.locked_connection() as db:
            row = db.execute('SELECT metadata_json FROM native_history_indexes WHERE cache_key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, key, value):
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        with self.database.transaction() as tx:
            tx.connection.execute('INSERT INTO native_history_indexes VALUES(?,?) ON CONFLICT(cache_key) DO UPDATE SET metadata_json=excluded.metadata_json', (key, raw))
