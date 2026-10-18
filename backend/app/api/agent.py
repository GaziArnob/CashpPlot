import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import agent, providers
from app.db import get_db
from app.deps import ai_limiter, get_business, needs, require_owner
from app.models import Business, ChatMessage
from app.schemas import ChatIn

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_owner), Depends(needs("agent"))])

SUGGESTED = [
    "Will I run short on cash next week?",
    "Who should I collect money from first?",
    "Why is my credit score what it is?",
    "How much can I safely borrow?",
    "What if my sales drop 10%?",
    "Where is my spending going up?",
]


def _history(db: Session, business: Business) -> list[dict]:
    rows = db.scalars(select(ChatMessage).where(ChatMessage.business_id == business.id)
                      .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(6)).all()
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


def _run(db: Session, business: Business, message: str) -> dict:
    history = _history(db, business)
    result = agent.answer(db, business, message, history)
    db.add(ChatMessage(business_id=business.id, role="user", content=message))
    db.add(ChatMessage(business_id=business.id, role="assistant", content=result["answer"]))
    db.commit()
    return result


@router.post("/chat", dependencies=[Depends(ai_limiter)])
def chat(body: ChatIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    return _run(db, business, body.message)


@router.post("/chat/stream", dependencies=[Depends(ai_limiter)])
def chat_stream(body: ChatIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    """Server-sent events: the answer arrives in small chunks, then a final 'done' event with metadata."""
    result = _run(db, business, body.message)

    def events():
        words = result["answer"].split(" ")
        for i in range(0, len(words), 4):
            chunk = " ".join(words[i:i + 4]) + (" " if i + 4 < len(words) else "")
            yield f"data: {json.dumps({'delta': chunk})}\n\n"
        meta = {k: v for k, v in result.items() if k != "answer"}
        yield f"event: done\ndata: {json.dumps(meta)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/history")
def history(business: Business = Depends(get_business), db: Session = Depends(get_db)):
    rows = db.scalars(select(ChatMessage).where(ChatMessage.business_id == business.id)
                      .order_by(ChatMessage.created_at, ChatMessage.id).limit(200)).all()
    return [{"role": r.role, "content": r.content, "created_at": r.created_at} for r in rows]


@router.get("/suggestions")
def suggestions(business: Business = Depends(get_business)):
    return {"questions": SUGGESTED, "llm_configured": providers.any_configured(business.ai_mode)}
