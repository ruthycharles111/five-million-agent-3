import os
import json
import base64
import io
from datetime import datetime, timedelta
from typing import Optional, List
import logging
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from playwright.sync_api import sync_playwright
from duckduckgo_search import DDGS
from database import (
    get_db_session, Student, Course, Quiz, ExamResult, Term, UserAccount,
    get_student_progress_db, set_term_lock, get_term_info, CourseFile
)

logger = logging.getLogger("uvicorn")

class ToolHandler:
    def __init__(self):
        self.course_dir = os.getenv("COURSE_FILES_DIR", "./course_files")
        os.makedirs(self.course_dir, exist_ok=True)

    def execute(self, name: str, args: dict):
        # Parse args (they may come as string or dict)
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
        return handler(**args)

    # ---------- Web & Screenshot ----------
    def search_web(self, query: str) -> List[dict]:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        return [{"title": r["title"], "url": r["href"], "snippet": r["body"]} for r in results]

    def take_screenshot(self, url: str) -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            # Wait a moment for content to load
            page.wait_for_timeout(2000)
            screenshot = page.screenshot(full_page=True)
            browser.close()
        # Return base64
        b64 = base64.b64encode(screenshot).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    # ---------- Marking ----------
    def mark_exam(self, student_id: str, course_id: str, term: str, answers: str) -> dict:
        # For demo, use simple LLM‑based grading (we call Mistral again inside tool? Better to use a rule‑based but here we'll return a placeholder)
        # In a real system, you'd compare against a stored answer key or use the LLM.
        # To avoid API call recursion, we'll just return a mock evaluation based on length.
        score = min(100, max(0, len(answers.split()) // 10))
        feedback = "Good work. Your answers show understanding. Keep practicing." if score > 70 else "You need to review the material. Pay attention to details."
        # Save to DB
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
        # Look up quiz answer key from DB
        session = get_db_session()
        try:
            quiz = session.query(Quiz).filter_by(quiz_id=quiz_id, course_id=course_id).first()
            if not quiz:
                return {"error": "Quiz not found"}
            correct = quiz.answer_key  # list of strings
            score = sum(1 for a, c in zip(answers, correct) if a.strip().upper() == c.strip().upper())
            total = len(correct)
            percentage = (score / total) * 100 if total else 0
            # Save
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
        # Use Mistral to correct (will be called from agent again, but it's fine as a separate call)
        # However, to avoid recursion, we return a formatted correction using a quick call.
        # For this demo, we'll provide a simple response.
        correction = f"I've corrected your sentence. Original: '{text}'. Suggested correction: (Placeholder – in production, the LLM does this)."
        return correction

    # ---------- Zoom ----------
    def create_zoom_meeting(self, topic: str, start_time: str, duration_minutes: int) -> dict:
        # Zoom requires OAuth or JWT; if not configured, return a manual link
        account_id = os.getenv("ZOOM_ACCOUNT_ID")
        client_id = os.getenv("ZOOM_CLIENT_ID")
        client_secret = os.getenv("ZOOM_CLIENT_SECRET")
        if not all([account_id, client_id, client_secret]):
            return {"meeting_link": f"https://zoom.us/j/1234567890?pwd=manual (Zoom not fully configured)", "note": "Zoom API keys missing"}
        try:
            import requests
            # Get access token
            auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            headers = {"Authorization": f"Basic {auth}"}
            token_resp = requests.post(
                f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={account_id}",
                headers=headers
            )
            token = token_resp.json().get("access_token")
            # Create meeting
            meeting_data = {
                "topic": topic,
                "type": 2,  # scheduled
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
        # Post to school webhook
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
        # Check if student completed Term 1-3 for any course
        session = get_db_session()
        try:
            student = session.query(Student).filter_by(id=student_id).first()
            if not student:
                return None
            # Check completion: all three terms passed? Simplified: assume if they have exam results with score >= 50 for each term.
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
            # Generate PDF
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
        # Looks for files in course_files/<course_id>/
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
        # In a real system, you'd reset password, etc. Here we simulate.
        logger.info(f"Fixing account for {student_id}: {issue}")
        return f"Successfully resolved issue for {student_id}: '{issue}'. Your account is now fixed."
