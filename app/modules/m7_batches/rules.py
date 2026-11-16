import csv,io,json,time
from decimal import Decimal
from app.config import SAMPLE_DIR
from app.errors import reject
from app.modules.m4_calculate.rules import status_label
from app.modules.m6_reconcile.rules import reconcile
def validate(options):
    if set(options)-{"sample","text","params"}:reject("PARAMETER","存在未知运行参数")
    if options.get("sample","dirty") not in {"dirty","clean","gb18030","pending"}:reject("SAMPLE","样例不存在")
    if "text" in options and not isinstance(options["text"],str):reject("CONTENT","文件内容须为文本")
    if not isinstance(options.get("params",{}),dict):reject("PARAMETER","参数须为对象")
    if options.get("params"):reject("PARAMETER","该项目无可调计算参数")
    return options
def apply_verification(body,outcome):
    if body.get("verification"):reject("VERIFIED","本批已完成核验，重跑不会重复扣款")
    for row in body["results"]:
        held=Decimal(row["pending"]);row["suspected"]=0;row["pending"]="0.00"
        if outcome=="确认":
            row["net"]=str(Decimal(row["net"])-held);row["credit"]=str(Decimal(row["gross"])-Decimal(row["net"]))
        row["payable"]=row["net"];row["status"]=status_label(row["reversed"],0)
    body["verification"]={"outcome":outcome,"at":time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    body["reconciliation"]=reconcile(body,json.loads((SAMPLE_DIR/"invoices.json").read_text()))
    return body
def csv_evidence(result):
    buffer=io.StringIO();writer=csv.writer(buffer)
    writer.writerow(["运行号","类别","来源行","原因码","原值"])
    rid=result["manifest"]["run_id"]
    for row in result.get("quarantine",[]):writer.writerow([rid,"隔离",row.get("line"),row.get("code"),json.dumps(row.get("raw",{}),ensure_ascii=False)])
    for row in result.get("invalid",[]):writer.writerow([rid,"无效",row.get("line"),row.get("code"),json.dumps(row,ensure_ascii=False)])
    for row in result.get("results",[]):writer.writerow([rid,"结论",row.get("line",""),row.get("status",""),json.dumps(row,ensure_ascii=False)])
    if result.get("verification"):writer.writerow([rid,"核验","",result["verification"]["outcome"],json.dumps(result["verification"],ensure_ascii=False)])
    return "﻿"+buffer.getvalue()
