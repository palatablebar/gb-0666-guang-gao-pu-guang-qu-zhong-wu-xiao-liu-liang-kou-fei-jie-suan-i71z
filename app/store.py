import sqlite3,json,time
from contextlib import contextmanager
from app.config import data_dir
from app.errors import reject
@contextmanager
def connect():
    d=data_dir();d.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(d/"records.sqlite",timeout=20)
    c.row_factory=sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,digest TEXT UNIQUE,body TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,decision TEXT NOT NULL DEFAULT '待复核')")
    c.execute("CREATE TABLE IF NOT EXISTS archives (run_id TEXT NOT NULL,revision INTEGER NOT NULL,body TEXT NOT NULL,decision TEXT NOT NULL,archived_at TEXT NOT NULL,PRIMARY KEY(run_id,revision))")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
def _archive(c,row):
    c.execute("INSERT OR IGNORE INTO archives(run_id,revision,body,decision,archived_at) VALUES(?,?,?,?,?)",(row["id"],row["revision"],row["body"],row["decision"],time.strftime("%Y-%m-%dT%H:%M:%S%z")))
def save(result):
    m=result["manifest"]
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO runs(id,digest,body) VALUES(?,?,?)",(m["run_id"],m["sha256"],json.dumps(result,ensure_ascii=False)))
    return fetch(m["run_id"])
def fetch(run_id):
    with connect() as c:row=c.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
    if row is None:reject("NOT_FOUND","运行不存在")
    data=json.loads(row["body"]);data["revision"]=row["revision"];data["decision"]=row["decision"];data["archives"]=versions(run_id)
    return data
def history():
    with connect() as c:return [dict(x) for x in c.execute("SELECT id,revision,decision FROM runs ORDER BY rowid DESC LIMIT 100")]
def versions(run_id):
    with connect() as c:return [dict(x) for x in c.execute("SELECT revision,decision,archived_at FROM archives WHERE run_id=? ORDER BY revision DESC",(run_id,))]
def _revision(value):
    if not isinstance(value,int) or isinstance(value,bool) or value<1:reject("VERSION","修订号须为正整数")
def review(run_id,revision,decision):
    _revision(revision)
    if decision not in ("通过","退回"):reject("DECISION","复核状态无效")
    with connect() as c:
        row=c.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        changed=c.execute("UPDATE runs SET revision=revision+1,decision=? WHERE id=? AND revision=?",(decision,run_id,revision)).rowcount
        if not changed:reject("STALE_VERSION","数据已更新，请重新载入")
        _archive(c,row)
    return fetch(run_id)
def verify(run_id,revision,outcome):
    _revision(revision)
    if outcome not in ("确认","推翻"):reject("DECISION","核验结论无效")
    from app.modules.m7_batches.rules import apply_verification
    with connect() as c:
        row=c.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        if row is None:reject("NOT_FOUND","运行不存在")
        body=apply_verification(json.loads(row["body"]),outcome)
        changed=c.execute("UPDATE runs SET body=?,revision=revision+1,decision=? WHERE id=? AND revision=?",(json.dumps(body,ensure_ascii=False),"已确认" if outcome=="确认" else "已释放",run_id,revision)).rowcount
        if not changed:reject("STALE_VERSION","数据已更新，请重新载入")
        _archive(c,row)
    return fetch(run_id)
def restore(run_id,revision,target):
    _revision(revision);_revision(target)
    with connect() as c:
        row=c.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        if row is None:reject("NOT_FOUND","运行不存在")
        archived=c.execute("SELECT * FROM archives WHERE run_id=? AND revision=?",(run_id,target)).fetchone()
        if archived is None:reject("NOT_FOUND","归档版本不存在")
        changed=c.execute("UPDATE runs SET body=?,decision=?,revision=revision+1 WHERE id=? AND revision=?",(archived["body"],archived["decision"],run_id,revision)).rowcount
        if not changed:reject("STALE_VERSION","数据已更新，请重新载入")
        _archive(c,row)
    return fetch(run_id)
