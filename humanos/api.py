"""HTTP interface. Explicit API key mandatory, including development mode."""
from __future__ import annotations

import os
import secrets
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from humanos.core import Store

app = FastAPI(title="HumanityOS", version="0.1.0", description="Evidence-first agent MVP")


def require_key(authorization: str | None = Header(default=None)) -> None:
    key = os.getenv("HUMANOS_API_KEY", "")
    if len(key) < 16:
        raise HTTPException(status_code=503, detail="Set HUMANOS_API_KEY (minimum 16 characters)")
    expected = "Bearer " + key
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def store() -> Store:
    return Store(os.getenv("HUMANOS_DB_PATH", "humanos.db"))


class GoalInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    keywords: list[str] = Field(min_length=1, max_length=20)


class CandidateInput(BaseModel):
    goal_id: str
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=10000)
    source_url: str = Field(min_length=1, max_length=2000)


class DecisionInput(BaseModel):
    decision: Literal["approved", "rejected"]


@app.get("/health")
def health():
    return {"status": "ok", "service": "humanos", "version": "0.1.0"}


@app.post("/v1/goals", dependencies=[Depends(require_key)], status_code=201)
def create_goal(body: GoalInput):
    try:
        return store().create_goal(body.title, body.keywords)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/goals", dependencies=[Depends(require_key)])
def goals():
    return store().list_goals()


@app.post("/v1/candidates", dependencies=[Depends(require_key)], status_code=201)
def add_candidate(body: CandidateInput):
    try:
        return store().add_candidate(**body.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/candidates", dependencies=[Depends(require_key)])
def candidates(goal_id: str | None = None):
    return store().list_candidates(goal_id)


@app.post("/v1/candidates/{candidate_id}/evaluate", dependencies=[Depends(require_key)])
def evaluate_candidate(candidate_id: str):
    try:
        return store().evaluate_candidate(candidate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/candidates/{candidate_id}/decision", dependencies=[Depends(require_key)])
def decide(candidate_id: str, body: DecisionInput):
    try:
        return store().review(candidate_id, body.decision)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/candidates/{candidate_id}/events", dependencies=[Depends(require_key)])
def events(candidate_id: str):
    if not store().get_candidate(candidate_id):
        raise HTTPException(status_code=404, detail="Candidate not found")
    return store().events(candidate_id)


@app.post("/v1/workers/run-once", dependencies=[Depends(require_key)])
def run_once():
    return store().run_queued()
