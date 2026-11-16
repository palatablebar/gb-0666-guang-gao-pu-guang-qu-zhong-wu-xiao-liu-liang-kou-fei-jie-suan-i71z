from fastapi import APIRouter
from app.modules.m7_batches.service import run
from app.errors import DomainError,http_error
router=APIRouter()
@router.get("/api/batches")
def evaluate(sample:str="dirty"):
    try:return run({"sample":sample})
    except DomainError as exc:raise http_error(exc)

@router.post("/api/runs")
def create_run(options:dict):
    try:return run(options)
    except DomainError as exc:raise http_error(exc)
@router.post("/api/runs/{run_id}/review")
def approve(run_id:str,options:dict):
    from app.store import review
    try:return review(run_id,options.get("revision"),options.get("decision"))
    except DomainError as exc:raise http_error(exc)
@router.post("/api/runs/{run_id}/verify")
def verify_run(run_id:str,options:dict):
    from app.store import verify
    try:return verify(run_id,options.get("revision"),options.get("outcome"))
    except DomainError as exc:raise http_error(exc)
@router.post("/api/runs/{run_id}/restore")
def restore_run(run_id:str,options:dict):
    from app.store import restore
    try:return restore(run_id,options.get("revision"),options.get("target"))
    except DomainError as exc:raise http_error(exc)
@router.get("/api/runs/{run_id}/versions")
def list_versions(run_id:str):
    from app.store import fetch,versions
    try:return {"run_id":fetch(run_id)["manifest"]["run_id"],"versions":versions(run_id)}
    except DomainError as exc:raise http_error(exc)
@router.get("/api/runs/{run_id}/evidence.csv")
def evidence(run_id:str):
    from fastapi.responses import Response
    from app.store import fetch
    from .rules import csv_evidence
    try:return Response(csv_evidence(fetch(run_id)),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=evidence.csv"})
    except DomainError as exc:raise http_error(exc)
