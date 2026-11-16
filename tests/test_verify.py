import pytest
from app.modules.m7_batches.service import run
from app.modules.m7_batches.rules import csv_evidence
from app.modules.m4_calculate.rules import settle
from app.modules.m3_model.service import run as model_run
from app.store import verify,restore,review,fetch,versions,history
from app.errors import DomainError

def test_pending_split(pending): # 待核验暂扣：不进扣款也不进实付
    r=run(pending)["reconciliation"]
    assert (r["gross"],r["credit"],r["net"],r["pending"],r["payable"])==("0.70","0.02","0.68","0.05","0.63")
    assert r["amount_ok"] is True and r["count_ok"] is True

def test_pending_status(pending):
    rows=run(pending)["results"]
    assert (rows[0]["status"],rows[0]["payable"],rows[0]["suspected"])==("已扣减·待核验","0.18",2)
    assert rows[1]["status"]=="待核验" and rows[2]["status"]=="通过"

def test_suspect_not_invalid(pending): # 疑似机器照常采信并计频次，仅标记待核验
    r=model_run(pending)
    assert r["invalid_counts"]=={"BOT":1}
    assert sum(1 for x in r["rows"] if x.get("suspect"))==3

def test_verify_confirm(pending): # 确认机器：暂扣转已确认扣款，实付不变
    a=run(pending);rid=a["manifest"]["run_id"]
    b=verify(rid,1,"确认");r=b["reconciliation"]
    assert (r["credit"],r["pending"],r["net"],r["payable"])==("0.07","0.00","0.63","0.63")
    assert r["amount_ok"] is True
    assert b["decision"]=="已确认" and b["revision"]==2 and b["verification"]["outcome"]=="确认"

def test_verify_release(pending): # 核验失败：暂扣释放并入实付补付
    a=run(pending);rid=a["manifest"]["run_id"]
    b=verify(rid,1,"推翻");r=b["reconciliation"]
    assert (r["credit"],r["pending"],r["payable"])==("0.02","0.00","0.68")
    assert b["decision"]=="已释放"

def test_no_double_deduct(pending): # 同批重跑与重复核验均不重复扣款
    a=run(pending);rid=a["manifest"]["run_id"]
    verify(rid,1,"确认")
    again=run(pending)
    assert again["manifest"]["run_id"]==rid and len(history())==1
    assert fetch(rid)["reconciliation"]["credit"]=="0.07"
    with pytest.raises(DomainError):verify(rid,1,"确认") # 旧修订号
    with pytest.raises(DomainError):verify(rid,2,"推翻") # 已核验
    assert fetch(rid)["reconciliation"]["credit"]=="0.07"

def test_restore(pending): # 核验失败后恢复旧账单及证据
    a=run(pending);rid=a["manifest"]["run_id"]
    verify(rid,1,"推翻")
    assert versions(rid)[0]["revision"]==1
    b=restore(rid,2,1)
    assert b["revision"]==3 and b["reconciliation"]["pending"]=="0.05" and b["reconciliation"]["payable"]=="0.63"
    assert "待核验" in csv_evidence(fetch(rid)) and "verification" not in fetch(rid)

def test_review_archives(clean): # 复核前自动归档旧版本
    a=run(clean);rid=a["manifest"]["run_id"]
    review(rid,1,"通过")
    assert versions(rid)[0]["revision"]==1
    b=restore(rid,2,1)
    assert b["decision"]=="待复核" and b["revision"]==3

def test_suspect_reversal(): # 疑似曝光被冲销时同步释放暂扣
    rows=[{"event_id":"A1","at":"2026-11-01T02:01:00+00:00","channel":"DSP-A","day":"2026-11-01","user_id":"U1","kind":"impression","cpm":"12.50","line":2,"suspect":True},
          {"event_id":"R1","at":"2026-11-01T03:00:00+00:00","channel":"DSP-A","day":"2026-11-01","user_id":"U1","kind":"reversal","ref":"A1","cpm":"12.50","line":3}]
    results,_,_=settle(rows)
    assert (results[0]["pending"],results[0]["payable"],results[0]["suspected"])==("0.00","0.00",0)

def test_verify_api_and_page(pending):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        data=c.post("/api/runs",json=pending).json();rid=data["manifest"]["run_id"]
        page=c.get("/batches?run_id="+rid)
        assert "已确认扣款" in page.text and "待核验金额" in page.text and "本次实付" in page.text
        ok=c.post(f"/api/runs/{rid}/verify",json={"revision":1,"outcome":"确认"})
        assert ok.status_code==200 and ok.json()["reconciliation"]["credit"]=="0.07"
        assert c.post(f"/api/runs/{rid}/verify",json={"revision":1,"outcome":"确认"}).status_code==409
        assert c.post(f"/api/runs/{rid}/verify",json={"revision":2,"outcome":"确认"}).status_code==409
        assert c.get(f"/api/runs/{rid}/versions").json()["versions"][0]["revision"]==1
        back=c.post(f"/api/runs/{rid}/restore",json={"revision":2,"target":1})
        assert back.status_code==200 and back.json()["reconciliation"]["pending"]=="0.05"
        assert "待核验" in c.get(f"/api/runs/{rid}/evidence.csv").text
