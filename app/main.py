from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import time
from .core.config import settings, parse_origins
from .api.data import router as data_router
import os

# Gemini setup (lazy import to keep cold-start light)
try:
    import google.generativeai as genai
    _HAS_GENAI = True
except Exception:
    _HAS_GENAI = False

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

_origins = parse_origins(settings.CORS_ORIGINS)
allow_origins = _origins if isinstance(_origins, list) else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=isinstance(_origins, list) and "*" not in allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatQuery(BaseModel):
    message: str

class ChatResponse(BaseModel):
    message: str
    sql_query: Optional[str] = None
    execution_time: Optional[float] = None

@app.get(f"{settings.API_PREFIX}/health")
async def health():
    return {"status": "ok"}

@app.post(f"{settings.API_PREFIX}/chat/query", response_model=ChatResponse)
async def chat_query(q: ChatQuery):
    start = time.time()
    # If Gemini key available, use it; otherwise fallback to mock
    if _HAS_GENAI and settings.GEMINI_API_KEY:
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model_name = settings.GEMINI_MODEL or "gemini-1.5-flash"
            model = genai.GenerativeModel(model_name)
            prompt = (
                "You are an assistant for an oceanography ARGO dashboard called FloatChat. "
                "Be concise. Answer the user's question."
            )
            resp = await _generate_async(model, f"{prompt}\nUser: {q.message}")
            msg = resp or "(empty response)"
            return ChatResponse(message=msg, sql_query=None, execution_time=time.time() - start)
        except Exception as e:
            # Fallback to mock on any error
            pass
    # Mock if no key or library
    sql = "SELECT platform_number, cycle_number FROM argo_profiles ORDER BY profile_date DESC LIMIT 10;"
    reply = f"(Mock) You asked: '{q.message}'."
    return ChatResponse(message=reply, sql_query=sql, execution_time=time.time() - start)


# Simple helper to call Gemini in an async-friendly way
import asyncio
async def _generate_async(model, content: str) -> str:
    loop = asyncio.get_event_loop()
    def _call():
        r = model.generate_content(content)
        # model may return text in .text or candidates
        return getattr(r, 'text', None) or (r.candidates[0].content.parts[0].text if getattr(r, 'candidates', None) else '')
    return await loop.run_in_executor(None, _call)

app.include_router(data_router, prefix=settings.API_PREFIX)
