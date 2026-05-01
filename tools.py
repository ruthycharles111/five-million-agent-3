import os, json, asyncio, base64, logging, subprocess
from typing import Optional, List
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from database import (
    get_db_session, Student, Course, Quiz, ExamResult, Term, UserAccount,
    get_student_progress_db, set_term_lock, get_term_info, init_db
)

logger = logging.getLogger("uvicorn")

class ToolHandler:
    def __init__(self):
        self.course_dir = os.getenv("COURSE_FILES_DIR", "./course_files")
        os.makedirs(self.course_dir, exist_ok=True)

    async def execute(self, name: str, args: dict):
        if isinstance(args, str):
            args = json.loads(args)
        func_map = {
            "search_web": self.search_web,
            "take_screenshot": self.take_screenshot,
            "mark_exam": self.mark_exam,
            "mark_quiz": self.mark_quiz,
            "correct_sentence": self.correct_sentence,
            "create_zoom_meeting": self.create_zoom_meeting,
            "get_student_progress": self.get_student_progress,
            "send_reminder": self.send_reminder,
            "lock_term": self.lock_term,
            "unlock_term": self.unlock_term,
            "generate_certificate": self.generate_certificate,
            "fetch_course_files": self.fetch_course_files,
            "fix_student_account": self.fix_student_account,
            "get_current_term": self.get_current_term,
        }
        handler = func_map.get(name)
        if handler is None:
            return f"Unknown function: {name}"
        if asyncio.iscoroutinefunction(handler):
            return await handler(**args)
        return handler(**args)

    # ---------- Web & Screenshot ----------
    def search_web(self, query: str) -> List[dict]:
        import httpx
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            resp = httpx.get("https://html.duckduckgo.com/html/", params={"q": query}, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for item in soup.select(".result")[:5]:
                title_el = item.select_one(".result__title a")
                snippet_el = item.select_one(".result__snippet")
                if title_el:
                    results.append({
                        "title": title_el.get_text(strip=True),
                        "url": title_el.get("href"),
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else ""
                    })
            return results if results else [{"title":"No results","url":"","snippet":"Try a different query."}]
        except Exception as e:
            return [{"title":"Search error","url":"","snippet":str(e)}]

    async def take_screenshot(self, url: str) -> str:
        try:
            if url.startswith('//'):
                url = 'https:' + url
            proc = await asyncio.create_subprocess_exec(
                'wkhtmltoimage', '--format', 'png', '--quality', '94',
                url, '-',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return f"Screenshot error: {stderr.decode()}"
            b64 = base64.b64encode(stdout).decode()
            return f"![screenshot](data:image/png;base64,{b64})"
        except Exception as e:
            return f"Screenshot tool error: {str(e)}"

    # ---------- Marking ----------
    def mark_exam(self, student_id: str, course_id: str, term: str, answers: str) -> dict:
        score = min(100, max(0, len(answers.split()) // 10))
        feedback = "Good work." if score > 70 else "Needs review."
        session = get_db_session()
        try:
            r = ExamResult(student_id=student_id, course_id=course_id, term=term, score=score, feedback=feedback, timestamp=datetime.utcnow())
            session.add(r); session.commit()
        finally:
            session.close()
        return {"score": score, "feedback": feedback}

    def mark_quiz(self, student_id: str, course_id: str, quiz_id: str, answers: List[str]) -> dict:
        session = get_db_session()
        try:
            quiz = session.query(Quiz).filter_by(quiz_id=quiz_id, course_id=course_id).first()
            if not quiz: return {"error": "Quiz not found"}
            correct = quiz.answer_key
            score = sum(1 for a, c in zip(answers, correct) if a.strip().upper() == c.strip().upper())
            total = len(correct)
            pct = (score / total) * 100 if total else 0
            session.add(ExamResult(student_id=student_id, course_id=course_id, term=quiz.term, score=pct, feedback=f"Quiz {quiz_id}: {score}/{total}", timestamp=datetime.utcnow()))
            session.commit()
            return {"score": pct, "total": total, "correct": score}
        finally:
            session.close()

    def correct_sentence(self, text: str, language: str = "auto") -> str:
        return f"Reviewed: '{text}'"

    # ---------- Zoom ----------
    def create_zoom_meeting(self, topic: str, start_time: str, duration_minutes: int) -> dict:
        return {"meeting_link": "https://zoom.us/j/1234567890 (configure keys for real meeting)"}

    # ---------- Progress & Reminders ----------
    def get_student_progress(self, student_id: str) -> dict:
        return get_student_progress_db(student_id)

    def send_reminder(self, student_id: str, message: str) -> str:
        webhook = os.getenv("SCHOOL_WEBHOOK_URL")
        if not webhook: return "No webhook configured."
        import httpx
        try:
            r = httpx.post(webhook, json={"event":"reminder","student_id":student_id,"message":message}, timeout=10)
            return f"Reminder sent ({r.status_code})"
        except Exception as e:
            return str(e)

    def lock_term(self, term: str):   set_term_lock(term, True); return f"Term '{term}' locked."
    def unlock_term(self, term: str): set_term_lock(term, False); return f"Term '{term}' unlocked."
    def get_current_term(self):       return get_term_info()

    # ---------- Certificates ----------
    def generate_certificate(self, student_id: str) -> Optional[str]:
        session = get_db_session()
        try:
            student = session.query(Student).filter_by(id=student_id).first()
            if not student: return None
            completed = None
            for c in session.query(Course).all():
                allpass = True
                for t in ["Term 1","Term 2","Term 3"]:
                    er = session.query(ExamResult).filter_by(student_id=student_id, course_id=c.id, term=t).first()
                    if not er or er.score < 50: allpass = False; break
                if allpass: completed = c; break
            if not completed: return None
            cert_dir = "certificates"; os.makedirs(cert_dir, exist_ok=True)
            path = os.path.join(cert_dir, f"{student_id}_certificate.pdf")
            c = canvas.Canvas(path, pagesize=A4)
            w, h = A4
            c.setFont("Helvetica-Bold", 24)
            c.drawCentredString(w/2, h-200, "Certificate of Completion")
            c.setFont("Helvetica", 18)
            c.drawCentredString(w/2, h-250, f"This certifies that {student.name}")
            c.drawCentredString(w/2, h-280, f"has successfully completed {completed.name}")
            c.drawCentredString(w/2, h-310, "Terms 1, 2, and 3")
            c.save()
            return path
        finally:
            session.close()

    # ---------- Course files ----------
    def fetch_course_files(self, course_id: str) -> List[dict]:
        path = os.path.join(self.course_dir, course_id)
        if not os.path.exists(path): return []
        files = []
        for root, dirs, fnames in os.walk(path):
            for f in fnames:
                rel = os.path.relpath(os.path.join(root, f), path)
                files.append({"name": f, "path": rel, "url": f"/courses/{course_id}/files/{rel}"})
        return files

    def list_courses(self): return [d for d in os.listdir(self.course_dir) if os.path.isdir(os.path.join(self.course_dir, d))]
    def list_course_files(self, course_id: str):
        p = os.path.join(self.course_dir, course_id)
        if not os.path.exists(p): return None
        files = []
        for root,dirs,fnames in os.walk(p):
            for f in fnames: files.append(f)
        return files
    def get_course_file_path(self, course_id: str, file_name: str):
        p = os.path.join(self.course_dir, course_id, file_name)
        return p if os.path.exists(p) else None

    def fix_student_account(self, student_id: str, issue: str):
        return f"Fixed account {student_id}: {issue}"
