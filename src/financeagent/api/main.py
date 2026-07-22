"""Chat API.

POST /api/chat  {"message": str, "session_id": str | null}
    -> Server-Sent Events stream. Event types (data is always a JSON object):

    event: session      data: {"session_id": "..."}          -- always first
    event: token        data: {"text": "..."}                -- streamed assistant text
    event: tool_call    data: {"id","name","args"}           -- agent invoked a tool
    event: tool_result  data: {"id","name","result"[,"image_base64"]}
                                                             -- image_base64 is a PNG, present
                                                                only for chart tools
    event: done         data: {"text": "..."}                -- full final answer; stream ends
    event: error        data: {"message": "..."}             -- stream ends

Pass the returned session_id in the next request to continue the conversation.
Omit it (or send null) to start a new one.
"""

import json
import threading
import uuid
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..agent import make_finance_agent
from ..agent.core import Agent
from ..config import PROJECT_ROOT

app = FastAPI(title="Finance Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass
class Session:
    agent: Agent
    lock: threading.Lock = field(default_factory=threading.Lock)


_sessions: dict[str, Session] = {}
_sessions_guard = threading.Lock()


def _get_or_create_session(session_id: str | None) -> tuple[str, Session]:
    with _sessions_guard:
        if session_id and session_id in _sessions:
            return session_id, _sessions[session_id]
        new_id = uuid.uuid4().hex
        session = Session(agent=make_finance_agent())
        _sessions[new_id] = session
        return new_id, session


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")

    try:
        session_id, session = _get_or_create_session(req.session_id)
    except RuntimeError as e:  # missing API key configuration
        raise HTTPException(status_code=503, detail=str(e))
    if not session.lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A response is already streaming for this session")

    def event_stream():
        try:
            yield {"event": "session", "data": json.dumps({"session_id": session_id})}
            agent = session.agent
            for event in agent.run_stream(req.message, messages=agent.messages):
                kind = event.pop("type")
                yield {"event": kind, "data": json.dumps(event)}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
        finally:
            session.lock.release()

    return EventSourceResponse(event_stream())


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str):
    with _sessions_guard:
        _sessions.pop(session_id, None)


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend")
