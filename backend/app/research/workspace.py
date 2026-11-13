import hashlib
import json
import time
from uuid import uuid4

from ..errors import AppError


def identifier(prefix):
    return prefix + '-' + uuid4().hex


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Workspace:
    def __init__(self, store, project, run):
        self.store, self.project, self.run = store, project, run
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS research_objects(
                project TEXT, id TEXT, run TEXT, kind TEXT, payload TEXT,
                PRIMARY KEY(project,id))''')

    def save(self, kind, value, object_id=None):
        key = object_id or identifier(kind)
        with self.store.connect() as db:
            old = db.execute('SELECT payload FROM research_objects WHERE project=? AND id=?', (self.project,key)).fetchone()
            if old:
                if json.loads(old['payload']) != value:
                    raise AppError('IMMUTABLE_OBJECT', '不能静默覆盖既有材料版本。', 409)
                return key
            db.execute('INSERT INTO research_objects VALUES(?,?,?,?,?)',
                       (self.project, key, self.run, kind, json.dumps(value, ensure_ascii=False)))
        self.store.artifact(self.run, kind, {'object_id': key, **value})
        return key

    def get(self, key):
        with self.store.connect() as db:
            row = db.execute('SELECT payload FROM research_objects WHERE project=? AND id=?', (self.project, key)).fetchone()
        if not row:
            raise AppError('OBJECT_NOT_FOUND', '当前项目中不存在该对象。', 404)
        return json.loads(row['payload'])


class Meter:
    def __init__(self, budget, workspace):
        self.limit, self.workspace = budget, workspace
        self.models = self.tools = self.tokens = 0
        self.started = time.monotonic()

    def charge(self, kind, name):
        if time.monotonic() - self.started >= self.limit.seconds:
            raise AppError('BUDGET_EXHAUSTED', '任务时间预算耗尽，保留现有产物。', 409)
        if kind == 'model':
            if self.models >= self.limit.model_calls:
                raise AppError('BUDGET_EXHAUSTED', '模型调用预算耗尽，保留未解决问题。', 409)
            self.models += 1
        else:
            if self.tools >= self.limit.tool_calls:
                raise AppError('BUDGET_EXHAUSTED', '工具调用预算耗尽，保留未解决问题。', 409)
            self.tools += 1
        self.workspace.save('usage', {'kind': kind, 'name': name, 'models': self.models,
                                     'tools': self.tools, 'elapsed': time.monotonic()-self.started})
