import os, json, logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse

from agent import AutonomousAgent
from database import init_db, get_db_session
from scheduler import start_scheduler

load_dotenv()
logger = logging.getLogger("uvicorn")
agent = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    init_db()
    agent = AutonomousAgent()
    start_scheduler(agent)
    logger.info("Agent started")
    yield
    if agent:
        agent.close()

# ----- WSGI wrapper for Gunicorn -----
from a2wsgi import ASGIMiddleware
app_fastapi = FastAPI(title="School Autonomous Agent API", lifespan=lifespan)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048

class ChatResponse(BaseModel):
    id: str = "agent-001"
    object: str = "chat.completion"
    created: int = 0
    model: str = "mistral-large-latest-agent"
    choices: list

@app_fastapi.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(request: ChatRequest):
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    try:
        result = await agent.run(messages, temperature=request.temperature, max_tokens=request.max_tokens)
    except Exception as e:
        logger.error(f"Agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResponse(choices=[{
        "index": 0,
        "message": {"role": "assistant", "content": result},
        "finish_reason": "stop"
    }])

@app_fastapi.get("/courses")
async def list_courses():
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")
    return agent.tools.list_courses()

@app_fastapi.get("/courses/{course_id}/files")
async def list_course_files(course_id: str):
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")
    files = agent.tools.list_course_files(course_id)
    if files is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return files

@app_fastapi.get("/courses/{course_id}/files/{file_name:path}")
async def download_course_file(course_id: str, file_name: str):
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")
    file_path = agent.tools.get_course_file_path(course_id, file_name)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

@app_fastapi.get("/certificates/{student_id}")
async def get_certificate(student_id: str):
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")
    path = agent.tools.generate_certificate(student_id)
    if not path:
        raise HTTPException(status_code=400, detail="Student not eligible")
    return FileResponse(path, media_type="application/pdf", filename="certificate.pdf")

@app_fastapi.post("/admin/term-lock")
async def admin_term_lock(action: str, term: str, secret: str = None):
    if secret != os.getenv("ADMIN_SECRET", "super-secret-change-me"):
        raise HTTPException(status_code=403)
    if action == "lock":
        agent.tools.lock_term(term)
    elif action == "unlock":
        agent.tools.unlock_term(term)
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    return {"status": "ok"}

@app_fastapi.get("/health")
def health():
    return {"status": "ok"}

# WSGI application needed by Gunicorn
application = ASGIMiddleware(app_fastapi)
