"""Local shared workspace. No connection is shared between threads or requests."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .errors import AppError


def dump(value):
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, runtime: Path):
        runtime.mkdir(parents=True, exist_ok=True)
        self.path = runtime / "workspace.sqlite3"
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, workdir TEXT NOT NULL, scope TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS papers (
                    scope TEXT, id TEXT, path TEXT, digest TEXT, paper TEXT,
                    chunks TEXT, PRIMARY KEY(scope,id));
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, project_id TEXT, conversation_id TEXT,
                    status TEXT, created_at TEXT, updated_at TEXT, question TEXT,
                    report TEXT, error_code TEXT);
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT, seq INTEGER, kind TEXT, payload TEXT,
                    created_at TEXT, PRIMARY KEY(run_id,seq));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover_interrupted(self):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='interrupted', error_code='SERVER_RESTART' WHERE status='running'")

    def bind(self, project_id, workdir, scope):
        with self.connect() as db:
            old = db.execute('SELECT workdir FROM projects WHERE id=?', (project_id,)).fetchone()
            if old and old['workdir'] != str(workdir):
                raise AppError('PROJECT_CONFLICT', '该项目 ID 已绑定其他工作目录，请使用新项目或恢复原目录。', 409)
            db.execute('INSERT OR REPLACE INTO projects VALUES (?,?,?)', (project_id, str(workdir), scope))

    def papers(self, scope):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM papers WHERE scope=?', (scope,))]

    def replace_papers(self, scope, records):
        with self.connect() as db:
            db.execute('DELETE FROM papers WHERE scope=?', (scope,))
            db.executemany('INSERT INTO papers VALUES (?,?,?,?,?,?)', [
                (scope, r['id'], r['path'], r['digest'], dump(r['paper']), dump(r['chunks'])) for r in records
            ])

    def source(self, project_id, paper_id):
        with self.connect() as db:
            r = db.execute('''SELECT p.*,j.workdir FROM papers p JOIN projects j ON p.scope=j.scope
                WHERE j.id=? AND p.id=?''', (project_id, paper_id)).fetchone()
            return dict(r) if r else None

    def start(self, run_id, request):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)', (
                run_id, request.project.id, request.conversationId, 'running', now, now,
                request.question, None, None))

    def artifact(self, run_id, kind, payload):
        with self.connect() as db:
            seq = db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM artifacts WHERE run_id=?', (run_id,)).fetchone()[0]
            db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?)', (
                run_id, seq, kind, dump(payload), datetime.now(timezone.utc).isoformat()))

    def finish(self, run_id, status, report=None, code=None):
        with self.connect() as db:
            db.execute('UPDATE runs SET status=?,report=?,error_code=?,updated_at=? WHERE id=?', (
                status, dump(report) if report is not None else None, code,
                datetime.now(timezone.utc).isoformat(), run_id))

    def run(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result['report'] = json.loads(result['report']) if result['report'] else None
            result['artifacts'] = [
                {'seq': r['seq'], 'kind': r['kind'], 'payload': json.loads(r['payload'])}
                for r in db.execute('SELECT * FROM artifacts WHERE run_id=? ORDER BY seq', (run_id,))
            ]
            return result

    def latest_report(self, project_id, conversation_id):
        with self.connect() as db:
            row = db.execute("SELECT report FROM runs WHERE project_id=? AND conversation_id=? AND status='completed' ORDER BY created_at DESC LIMIT 1",
                             (project_id, conversation_id)).fetchone()
            return json.loads(row['report']) if row and row['report'] else None
