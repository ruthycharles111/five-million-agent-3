import os
import json
import logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
from dotenv import load_dotenv
from contextlib import asynccontextmanager

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
    # cleanup
    if agent:
        agent.close()

app = FastAPI(title="School Autonomous Agent API", lifespan=lifespan)
@app.get("/health")
def health():
    return {"status":"ok"}

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

@app.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(request: ChatRequest):
    """Main endpoint – call just like an LLM API."""
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

@app.get("/courses")
async def list_courses():
    """List all available courses."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")
    return agent.tools.list_courses()

@app.get("/courses/{course_id}/files")
async def list_course_files(course_id: str):
    """List files for a specific course."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")
    files = agent.tools.list_course_files(course_id)
    if files is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return files

@app.get("/courses/{course_id}/files/{file_name:path}")
async def download_course_file(course_id: str, file_name: str):
    """Download a course file."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")
    file_path = agent.tools.get_course_file_path(course_id, file_name)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    from fastapi.responses import FileResponse
    return FileResponse(file_path)

@app.get("/certificates/{student_id}")
async def get_certificate(student_id: str):
    """Generate/download a certificate for a student who completed all terms."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")
    path = agent.tools.generate_certificate(student_id)
    if not path:
        raise HTTPException(status_code=400, detail="Student not eligible")
    from fastapi.responses import FileResponse
    return FileResponse(path, media_type="application/pdf", filename="certificate.pdf")

@app.post("/admin/term-lock")
async def admin_term_lock(action: str, term: str, secret: str = None):
    """Admin endpoint to manually lock/unlock a term. Requires secret=os.environ['ADMIN_SECRET']."""
    if secret != os.getenv("ADMIN_SECRET", "super-secret-change-me"):
        raise HTTPException(status_code=403)
    if action == "lock":
        agent.tools.lock_term(term)
    elif action == "unlock":
        agent.tools.unlock_term(term)
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
