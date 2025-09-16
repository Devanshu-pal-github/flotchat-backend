from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import time
from .core.config import settings, parse_origins
from .api.data import router as data_router

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
    # Very basic mock: echo and produce a sample SQL
    sql = "SELECT * FROM argo_profiles LIMIT 10;"
    reply = f"You asked: '{q.message}'. Mock SQL: {sql}"
    return ChatResponse(message=reply, sql_query=sql, execution_time=time.time() - start)

app.include_router(data_router, prefix=settings.API_PREFIX)
