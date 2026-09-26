"""Only this module knows SQLite. A transaction is the unit of repository access.

Authentication records are deliberately separate from owner-scoped business rows.
JSON bodies are internal aggregates, not a second set of transport DTOs.
"""
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .common import canonical

SCHEMA_VERSION = 1
MIGRATIONS = {1: """
CREATE TABLE auth (key TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE records (
 ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
 owner TEXT NOT NULL CHECK(length(owner)>0), kind TEXT NOT NULL, id TEXT NOT NULL,
 worker TEXT NOT NULL, store TEXT NOT NULL, parent TEXT NOT NULL, body TEXT NOT NULL,
 UNIQUE(owner,kind,id));
CREATE INDEX records_scope ON records(owner,kind,worker,store,parent,ordinal);
CREATE TABLE inbox (
 owner TEXT NOT NULL CHECK(length(owner)>0), worker TEXT NOT NULL, store TEXT NOT NULL,
 event_id TEXT NOT NULL, first_seq INTEGER NOT NULL, last_seq INTEGER NOT NULL,
 body TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(owner,event_id), UNIQUE(owner,worker,store,last_seq));
CREATE INDEX inbox_ranges ON inbox(owner,worker,store,first_seq,last_seq);
CREATE TABLE browser_outbox (
 ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
 owner TEXT NOT NULL CHECK(length(owner)>0), body TEXT NOT NULL);
CREATE INDEX browser_owner ON browser_outbox(owner,ordinal);
"""}


class Repository:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        try:
            self.migrate()
        except BaseException:
            self.connection.close()
            raise

    def migrate(self):
        with self.lock:
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("Database schema is newer than this server")
            for target in range(version + 1, SCHEMA_VERSION + 1):
                self.connection.executescript("BEGIN IMMEDIATE;\n" + MIGRATIONS[target] + f"\nPRAGMA user_version={target};\nCOMMIT;")

    @contextmanager
    def transaction(self):
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield UnitOfWork(self.connection)
                self.connection.execute("COMMIT")
            except BaseException:
                self.connection.execute("ROLLBACK")
                raise

    def backup(self, destination):
        path = Path(destination).resolve()
        source = Path(self.connection.execute("PRAGMA database_list").fetchone()[2]).resolve()
        if path == source or path.exists():
            raise ValueError("Backup destination must be a new file")
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, sqlite3.connect(str(path)) as output:
            self.connection.backup(output)

    def close(self):
        with self.lock:
            self.connection.close()


class UnitOfWork:
    def __init__(self, connection):
        self.db = connection

    def auth_get(self, key):
        row = self.db.execute("SELECT body FROM auth WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def auth_put(self, key, body, owner=""):
        self.db.execute("INSERT INTO auth VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET owner=excluded.owner,body=excluded.body", (key, owner, canonical(body)))

    def auth_list(self, prefix):
        return [json.loads(r[0]) for r in self.db.execute("SELECT body FROM auth WHERE substr(key,1,?)=?", (len(prefix), prefix))]

    def get(self, owner, kind, identifier):
        row = self.db.execute("SELECT body FROM records WHERE owner=? AND kind=? AND id=?", (owner, kind, identifier)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, owner, kind, identifier, body, *, worker="", store="", parent=""):
        self.db.execute("""INSERT INTO records(owner,kind,id,worker,store,parent,body) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(owner,kind,id) DO UPDATE SET body=excluded.body,worker=excluded.worker,store=excluded.store,parent=excluded.parent""",
                        (owner, kind, identifier, worker, store, parent, canonical(body)))

    def list(self, owner, kind, *, worker=None, store=None, parent=None, limit=None, offset=0):
        query = "SELECT body FROM records WHERE owner=? AND kind=?"
        params = [owner, kind]
        for column, value in (("worker", worker), ("store", store), ("parent", parent)):
            if value is not None:
                query += f" AND {column}=?"
                params.append(value)
        query += " ORDER BY ordinal"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return [json.loads(r[0]) for r in self.db.execute(query, params)]

    def event_id(self, owner, event_id):
        row = self.db.execute("SELECT body FROM inbox WHERE owner=? AND event_id=?", (owner, event_id)).fetchone()
        return json.loads(row[0]) if row else None

    def overlaps(self, owner, worker, store, first, last):
        return [json.loads(r[0]) for r in self.db.execute("SELECT body FROM inbox WHERE owner=? AND worker=? AND store=? AND first_seq<=? AND last_seq>=?", (owner, worker, store, last, first))]

    def event_put(self, owner, event):
        self.db.execute("INSERT INTO inbox(owner,worker,store,event_id,first_seq,last_seq,body) VALUES(?,?,?,?,?,?,?)", (owner, event["workerId"], event["workerStoreId"], event["eventId"], event.get("firstSeq", event["seq"]), event["seq"], canonical(event)))

    def next_event(self, owner, worker, store, first):
        row = self.db.execute("SELECT body FROM inbox WHERE owner=? AND worker=? AND store=? AND first_seq=?", (owner, worker, store, first)).fetchone()
        return json.loads(row[0]) if row else None

    def event_applied(self, owner, event_id):
        self.db.execute("UPDATE inbox SET applied=1 WHERE owner=? AND event_id=?", (owner, event_id))

    def browser_add(self, owner, body):
        return self.db.execute("INSERT INTO browser_outbox(owner,body) VALUES(?,?)", (owner, canonical(body))).lastrowid

    def browser_tail(self, owner):
        return self.db.execute("SELECT COALESCE(MAX(ordinal),0) FROM browser_outbox WHERE owner=?", (owner,)).fetchone()[0]

    def browser_after(self, owner, after, limit):
        return [(r[0], json.loads(r[1])) for r in self.db.execute("SELECT ordinal,body FROM browser_outbox WHERE owner=? AND ordinal>? ORDER BY ordinal LIMIT ?", (owner, after, limit))]
