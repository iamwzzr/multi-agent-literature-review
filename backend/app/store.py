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
                    chunks TEXT, fingerprint TEXT, PRIMARY KEY(scope,id));
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, project_id TEXT, conversation_id TEXT,
                    status TEXT, created_at TEXT, updated_at TEXT, question TEXT,
                    report TEXT, error_code TEXT, error_details TEXT);
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT, seq INTEGER, kind TEXT, payload TEXT,
                    created_at TEXT, PRIMARY KEY(run_id,seq));
                CREATE INDEX IF NOT EXISTS conversation_runs ON runs(project_id,conversation_id,created_at);
            ''')
            if 'fingerprint' not in {column['name'] for column in db.execute('PRAGMA table_info(papers)')}:
                db.execute('ALTER TABLE papers ADD COLUMN fingerprint TEXT')
            if 'error_details' not in {column['name'] for column in db.execute('PRAGMA table_info(runs)')}:
                db.execute('ALTER TABLE runs ADD COLUMN error_details TEXT')

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

    @staticmethod
    def check_workdir(db, project_id, workdir):
        old = db.execute('SELECT workdir FROM projects WHERE id=?', (project_id,)).fetchone()
        if old and old['workdir'] != str(workdir):
            raise AppError('PROJECT_CONFLICT', '该项目 ID 已绑定其他工作目录，请使用新项目或恢复原目录。', 409)
        return old is not None

    def validate_project(self, project_id, workdir):
        with self.connect() as db:
            return self.check_workdir(db, project_id, workdir)

    def bind(self, project_id, workdir, scope):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO projects VALUES (?,?,?)', (project_id, str(workdir), scope))
            self.check_workdir(db, project_id, workdir)

    def papers(self, scope):
        with self.connect() as db:
            return {row['path']: {**dict(row), 'paper': json.loads(row['paper']), 'chunks': json.loads(row['chunks'])}
                    for row in db.execute('SELECT * FROM papers WHERE scope=?', (scope,))}

    def update_index(self, project_id, workdir, scope, changed, removed):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO projects VALUES (?,?,?)', (project_id, str(workdir), scope))
            self.check_workdir(db, project_id, workdir)
            db.executemany('DELETE FROM papers WHERE scope=? AND id=?', ((scope, item) for item in removed))
            db.executemany('''INSERT OR REPLACE INTO papers(scope,id,path,digest,paper,chunks,fingerprint)
                              VALUES (?,?,?,?,?,?,?)''', (
                (scope, row['id'], row['path'], row['digest'], dump(row['paper']), dump(row['chunks']), row['fingerprint'])
                for row in changed))
            db.execute('UPDATE projects SET scope=? WHERE id=? AND scope<>?', (scope, project_id, scope))

    def source(self, project_id, paper_id):
        with self.connect() as db:
            r = db.execute('''SELECT p.path,p.digest FROM papers p JOIN projects j ON p.scope=j.scope
                WHERE j.id=? AND p.id=?''', (project_id, paper_id)).fetchone()
            return dict(r) if r else None

    def start(self, run_id, request):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute('''INSERT INTO runs(id,project_id,conversation_id,status,created_at,updated_at,question)
                          VALUES (?,?,?,?,?,?,?)''', (
                run_id, request.project.id, request.conversationId, 'running', now, now,
                request.question))

    def artifact(self, run_id, kind, payload):
        with self.connect() as db:
            seq = db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM artifacts WHERE run_id=?', (run_id,)).fetchone()[0]
            db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?)', (
                run_id, seq, kind, dump(payload), datetime.now(timezone.utc).isoformat()))

    def finish(self, run_id, status, report=None, code=None, error=None):
        with self.connect() as db:
            db.execute("""UPDATE runs SET status=?,report=?,error_code=?,error_details=?,updated_at=?
                          WHERE id=? AND status='running'""", (
                status, dump(report) if report is not None else None, error['code'] if error else code,
                dump(error) if error else None, datetime.now(timezone.utc).isoformat(), run_id))

    def run(self, run_id, project_id=None, conversation_id=None, include_artifacts=True):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if (not row or project_id is not None and row['project_id'] != project_id
                    or conversation_id is not None and row['conversation_id'] != conversation_id):
                return None
            result = dict(row)
            result['report'] = json.loads(result['report']) if result['report'] else None
            error = result.pop('error_details')
            if error:
                result['error'] = json.loads(error)
            if include_artifacts:
                result['artifacts'] = [
                    {'seq': r['seq'], 'kind': r['kind'], 'payload': json.loads(r['payload'])}
                    for r in db.execute('SELECT * FROM artifacts WHERE run_id=? ORDER BY seq', (run_id,))
                ]
            return result

    def delete_conversation(self, project_id, conversation_id):
        with self.connect() as db:
            key = (project_id, conversation_id)
            db.execute('''DELETE FROM artifacts WHERE run_id IN
                          (SELECT id FROM runs WHERE project_id=? AND conversation_id=?)''', key)
            db.execute('DELETE FROM runs WHERE project_id=? AND conversation_id=?', key)

    def latest_report(self, project_id, conversation_id):
        with self.connect() as db:
            row = db.execute("SELECT report FROM runs WHERE project_id=? AND conversation_id=? AND status='completed' ORDER BY created_at DESC LIMIT 1",
                             (project_id, conversation_id)).fetchone()
            return json.loads(row['report']) if row and row['report'] else None
