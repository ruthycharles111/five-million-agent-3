import os
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_db_session, Student, Term

logger = logging.getLogger("uvicorn")

scheduler = BackgroundScheduler()

def send_daily_greetings(agent):
    """Called every day at 8 AM UTC."""
    webhook = os.getenv("SCHOOL_WEBHOOK_URL")
    if not webhook:
        return
    # Get all students
    session = get_db_session()
    try:
        students = session.query(Student).all()
        for s in students:
            message = f"Good morning, {s.name}! 🌞 Have a productive day of learning."
            agent.tools.send_reminder(s.id, message)  # reuse reminder webhook
    except Exception as e:
        logger.error(f"Daily greetings error: {e}")
    finally:
        session.close()

def check_pending_work_and_remind(agent):
    """Check for students who haven't completed activities and remind them."""
    # For simplicity, we'll check exam results and if missing, remind.
    # This is a placeholder; in a real system you'd compare against course requirements.
    session = get_db_session()
    try:
        students = session.query(Student).all()
        # Fetch all terms that are unlocked
        terms = session.query(Term).filter_by(locked=False).all()
        for s in students:
            # Very basic check: if student has no exam results in any unlocked term, remind.
            from database import ExamResult
            for term in terms:
                res = session.query(ExamResult).filter_by(student_id=s.id, term=term.name).first()
                if not res:
                    agent.tools.send_reminder(s.id, f"Reminder: You haven't submitted your work for {term.name}. Please complete it.")
    except Exception as e:
        logger.error(f"Reminder check error: {e}")
    finally:
        session.close()

def auto_lock_terms(agent):
    """Check current date and lock/unlock terms based on configured dates (stub)."""
    # This would use Term start/end dates. For now, nothing.
    pass

def start_scheduler(agent):
    scheduler.add_job(send_daily_greetings, 'cron', hour=8, minute=0, args=[agent], id='greetings')
    scheduler.add_job(check_pending_work_and_remind, 'cron', hour=9, minute=0, args=[agent], id='reminders')
    scheduler.add_job(auto_lock_terms, 'cron', hour=0, minute=5, args=[agent], id='term_locks')
    scheduler.start()
