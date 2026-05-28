"""FastAPI server exposing the six poker-buddy tools as webhook endpoints.

ElevenLabs ConvAI calls these endpoints when its underlying LLM (Claude Opus
4.7 configured in the dashboard) invokes a server tool. Each endpoint accepts
the tool's argument JSON and returns the tool's result JSON.

We use Pydantic for input validation. We don't enforce auth on the public
tunnel — protection is via Cloudflare Tunnel's randomized hostname + a shared
secret header you can configure later. For personal use, that's adequate.

Run locally:
    uv run uvicorn backend.main:app --reload --port 8765
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.db import init_db
from backend.tools.memory import memory_read, memory_write, opponent_profile_update
from backend.tools.postflop_lookup import postflop_lookup
from backend.tools.preflop_lookup import preflop_lookup
from backend.tools.theory_lookup import theory_lookup

load_dotenv()
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("poker-buddy")

# Ensure schema exists at startup.
init_db()

app = FastAPI(
    title="Poker Buddy",
    description="Voice-first NLH cash poker discussion partner. Tool webhooks for ElevenLabs ConvAI.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ConvAI calls server-to-server; frontend doesn't talk to us.
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


_SHARED_SECRET = os.environ.get("BUDDY_SHARED_SECRET", "")


@app.middleware("http")
async def shared_secret_guard(request: Request, call_next):
    """If BUDDY_SHARED_SECRET is set, require X-Buddy-Secret on tool calls.

    /health is always public so the tunnel can be probed.
    """
    if request.url.path.startswith("/tools/") and _SHARED_SECRET:
        provided = request.headers.get("X-Buddy-Secret", "")
        if provided != _SHARED_SECRET:
            return _json_error(401, "missing or wrong X-Buddy-Secret header")
    return await call_next(request)


def _json_error(status: int, msg: str):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status, content={"error": msg})


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------

class PreflopLookupIn(BaseModel):
    format: str = Field(..., description="'hu' or '6max'")
    position: str = Field(..., description="btn/bb/co/mp/utg/sb")
    hand: str = Field(..., description="Range notation 'JTs' or concrete 'JhTh'")
    stack_depth_bb: float = 100.0
    action_so_far: list[str] | None = None


class PostflopLookupIn(BaseModel):
    format: str
    hand: str
    board: str
    position: str = "btn"
    line: list[str] | None = None
    stack_depth_bb: float = 100.0
    is_4bet_pot: bool = False


class TheoryLookupIn(BaseModel):
    query: str
    k: int = 3


class MemoryReadIn(BaseModel):
    topic: str


class MemoryWriteIn(BaseModel):
    kind: str
    content: dict[str, Any]


class OpponentUpdateIn(BaseModel):
    label: str
    observation: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "poker-buddy", "version": "0.1.0"}


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "poker-buddy",
        "tools": [
            "POST /tools/preflop_lookup",
            "POST /tools/postflop_lookup",
            "POST /tools/theory_lookup",
            "POST /tools/memory_read",
            "POST /tools/memory_write",
            "POST /tools/opponent_profile_update",
        ],
    }


@app.post("/tools/preflop_lookup")
def tool_preflop_lookup(body: PreflopLookupIn) -> dict[str, Any]:
    log.info("preflop_lookup: %s %s %s", body.format, body.position, body.hand)
    return preflop_lookup(
        format=body.format,
        position=body.position,
        hand=body.hand,
        stack_depth_bb=body.stack_depth_bb,
        action_so_far=body.action_so_far,
    )


@app.post("/tools/postflop_lookup")
def tool_postflop_lookup(body: PostflopLookupIn) -> dict[str, Any]:
    log.info("postflop_lookup: %s %s %s on %s", body.format, body.position, body.hand, body.board)
    return postflop_lookup(
        format=body.format,
        hand=body.hand,
        board=body.board,
        position=body.position,
        line=body.line,
        stack_depth_bb=body.stack_depth_bb,
        is_4bet_pot=body.is_4bet_pot,
    )


@app.post("/tools/theory_lookup")
def tool_theory_lookup(body: TheoryLookupIn) -> dict[str, Any]:
    log.info("theory_lookup: %r k=%d", body.query, body.k)
    return theory_lookup(query=body.query, k=body.k)


@app.post("/tools/memory_read")
def tool_memory_read(body: MemoryReadIn) -> dict[str, Any]:
    log.info("memory_read: %s", body.topic)
    return memory_read(topic=body.topic)


@app.post("/tools/memory_write")
def tool_memory_write(body: MemoryWriteIn) -> dict[str, Any]:
    log.info("memory_write: %s", body.kind)
    return memory_write(kind=body.kind, content=body.content)


@app.post("/tools/opponent_profile_update")
def tool_opponent_profile_update(body: OpponentUpdateIn) -> dict[str, Any]:
    log.info("opponent_profile_update: %s", body.label)
    return opponent_profile_update(label=body.label, observation=body.observation)
