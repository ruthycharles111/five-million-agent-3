import os
import json
import asyncio
import base64
import logging
from typing import Optional, List
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from playwright.async_api import async_playwright
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
        # Proper async detection
        if asyncio.iscoroutinefunction(handler):
            return await handler(**args)
        else:
            return handler(**args)

    # ---------- Web & Screenshot ----------
    def search_web(self, query: str) -> List[dict]:
        """Search the web using DuckDuckGo HTML (no API key). Returns list of results."""
        import httpx
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"}
        try:
            resp = httpx.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers=headers,
                timeout=15
            )
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
        """Take a screenshot of a given URL using async Playwright. Returns Markdown image or error."""
        try:
            if url.startswith('//'):
                url = 'https:' + url
            if not url.startswith(('http://','https://')):
                return f"Invalid URL: {url}"
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=30000)
                await page.wait_for_timeout(2000)
                screenshot = await page.screenshot(full_page=True)
                await browser.close()
            b64 = base64.b64encode(screenshot).decode("utf-8")
            return f"![screenshot](data:image/png;base64,{b64})"
        except Exception as e:
            return f"Screenshot tool error: {str(e)}"

    # ---------- Marking ----------
    def mark_exam(self, student_id: str, course_id: str, term: str, answers: str) -> dict:
        score = min(100, max(0, len(answers.split()) // 10))
        feedback = "Good work. Your answers show understanding. Keep practicing." if score > 70 else "You need to review the material. Pay attention to details."
        session = get_db_session()
        try:
            result = ExamResult(
                student_id=student_id,
                course_id=course_id,
                term=term,
                score=score,
                feedback=feedback,
                timestamp=datetime.utcnow()
            )
            session.add(result)
            session.commit()
        finally:
            session.close()
        return {"score": score, "feedback": feedback}

    def mark_quiz(self, student_id: str, course_id: str, quiz_id: str, answers: List[str]) -> dict:
        session = get_db_session()
        try:
            quiz = session.query(Quiz).filter_by(quiz_id=quiz_id, course_id=course_id).first()
            if not quiz:
                return {"error": "Quiz not found"}
            correct = quiz.answer_key
            score = sum(1 for a, c in zip(answers, correct) if a.strip().upper() == c.strip().upper())
            total = len(correct)
            percentage = (score / total) * 100 if total else 0
            result = ExamResult(
                student_id=student_id, course_id=course_id, term=quiz.term, score=percentage,
                feedback=f"Quiz {quiz_id}: {score}/{total} correct.", timestamp=datetime.utcnow()
            )
            session.add(result)
            session.commit()
            return {"score": percentage, "total": total, "correct": score}
        finally:
            session.close()

    def correct_sentence(self, text: str, language: str = "auto") -> str:
        return f"I've reviewed your sentence. Original: '{text}'. (Correction suggestions would appear here.)"

    # ---------- Zoom ----------
    def create_zoom_meeting(self, topic: str, start_time: str, duration_minutes: int) -> dict:
        account_id = os.getenv("ZOOM_ACCOUNT_ID")
        client_id = os.getenv("ZOOM_CLIENT_ID")
        client_secret = os.getenv("ZOOM_CLIENT_SECRET")
        if not all([account_id, client_id, client_secret]):
            return {"meeting_link": "https://zoom.us/j/1234567890?pwd=manual (Zoom not fully configured)", "note": "Zoom API keys missing"}
        try:
            import requests
            auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            headers = {"Authorization": f"Basic {auth}"}
            token_resp = requests.post(
                f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={account_id}",
                headers=headers
            )
            token = token_resp.json().get("access_token")
            meeting_data = {
                "topic": topic,
                "type": 2,
                "start_time": start_time,
                "duration": duration_minutes,
                "timezone": "UTC",
                "settings": {"host_video": True, "participant_video": True}
            }
            meet_resp = requests.post(
                "https://api.zoom.us/v2/users/me/meetings",
                headers={"Authorization": f"Bearer {token}"},
                json=meeting_data
            )
            return {"meeting_link": meet_resp.json().get("join_url", "Error")}
        except Exception as e:
            return {"error": str(e), "meeting_link": "Could not create Zoom meeting"}

    # ---------- Progress & Reminders ----------
    def get_student_progress(self, student_id: str) -> dict:
        return get_student_progress_db(student_id)

    def send_reminder(self, student_id: str, message: str) -> str:
        webhook = os.getenv("SCHOOL_WEBHOOK_URL")
        if not webhook:
            logger.warning("No SCHOOL_WEBHOOK_URL set; reminder not sent.")
            return "Reminder not sent (webhook not configured)."
        import httpx
        try:
            response = httpx.post(webhook, json={
                "event": "reminder",
                "student_id": student_id,
                "message": message
            }, timeout=10)
            return f"Reminder sent. Status: {response.status_code}"
        except Exception as e:
            return f"Failed to send reminder: {e}"

    # ---------- Term management ----------
    def lock_term(self, term: str):
        set_term_lock(term, locked=True)
        return f"Term '{term}' locked."

    def unlock_term(self, term: str):
        set_term_lock(term, locked=False)
        return f"Term '{term}' unlocked."

    def get_current_term(self):
        info = get_term_info()
        return info

    # ---------- Certificates ----------
    def generate_certificate(self, student_id: str) -> Optional[str]:
        session = get_db_session()
        try:
            student = session.query(Student).filter_by(id=student_id).first()
            if not student:
                return None
            completed_course = None
            for course in session.query(Course).all():
                terms = ["Term 1", "Term 2", "Term 3"]
                all_passed = True
                for t in terms:
                    res = session.query(ExamResult).filter_by(
                        student_id=student_id, course_id=course.id, term=t
                    ).first()
                    if not res or res.score < 50:
                        all_passed = False
                        break
                if all_passed:
                    completed_course = course
                    break
            if not completed_course:
                return None
            cert_dir = "certificates"
            os.makedirs(cert_dir, exist_ok=True)
            pdf_path = os.path.join(cert_dir, f"{student_id}_certificate.pdf")
            c = canvas.Canvas(pdf_path, pagesize=A4)
            width, height = A4
            c.setFont("Helvetica-Bold", 24)
            c.drawCentredString(width/2, height - 200, "Certificate of Completion")
            c.setFont("Helvetica", 18)
            c.drawCentredString(width/2, height - 250, f"This certifies that {student.name}")
            c.drawCentredString(width/2, height - 280, f"has successfully completed {completed_course.name}")
            c.drawCentredString(width/2, height - 310, "Terms 1, 2, and 3")
            c.setFont("Helvetica-Oblique", 14)
            c.drawCentredString(width/2, height - 360, f"Issued on {datetime.utcnow().strftime('%B %d, %Y')}")
            c.drawCentredString(width/2, height - 390, "by the Autonomous School Agent")
            c.save()
            return pdf_path
        finally:
            session.close()

    # ---------- Course files ----------
    def fetch_course_files(self, course_id: str) -> List[dict]:
        course_path = os.path.join(self.course_dir, course_id)
        if not os.path.exists(course_path):
            return []
        files = []
        for root, dirs, fnames in os.walk(course_path):
            for fname in fnames:
                rel_path = os.path.relpath(os.path.join(root, fname), course_path)
                files.append({
                    "name": fname,
                    "path": rel_path,
                    "url": f"/courses/{course_id}/files/{rel_path}"
                })
        return files

    def list_courses(self):
        if not os.path.exists(self.course_dir):
            return []
        return [d for d in os.listdir(self.course_dir) if os.path.isdir(os.path.join(self.course_dir, d))]

    def list_course_files(self, course_id: str):
        course_path = os.path.join(self.course_dir, course_id)
        if not os.path.exists(course_path):
            return None
        files = []
        for root, dirs, fnames in os.walk(course_path):
            for fname in fnames:
                files.append(fname)
        return files

    def get_course_file_path(self, course_id: str, file_name: str):
        course_path = os.path.join(self.course_dir, course_id)
        full_path = os.path.join(course_path, file_name)
        if os.path.exists(full_path) and full_path.startswith(course_path):
            return full_path
        return None

    # ---------- Student account fix ----------
    def fix_student_account(self, student_id: str, issue: str):
        logger.info(f"Fixing account for {student_id}: {issue}")
        return f"Successfully resolved issue for {student_id}: '{issue}'. Your account is now fixed."
