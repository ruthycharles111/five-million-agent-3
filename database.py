import os
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./school_agent.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------- Models (minimal) ----------
class Student(Base):
    __tablename__ = "students"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String)

class Course(Base):
    __tablename__ = "courses"
    id = Column(String, primary_key=True)
    name = Column(String)

class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    quiz_id = Column(String)
    course_id = Column(String)
    term = Column(String)
    # Store answer key as JSON string
    answer_key_json = Column(String)

    @property
    def answer_key(self):
        import json
        return json.loads(self.answer_key_json)

class ExamResult(Base):
    __tablename__ = "exam_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String)
    course_id = Column(String)
    term = Column(String)
    score = Column(Float)
    feedback = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Term(Base):
    __tablename__ = "terms"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True)  # "Term 1", "Term 2", "Term 3"
    locked = Column(Boolean, default=False)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)

class UserAccount(Base):
    __tablename__ = "user_accounts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String, unique=True)
    password_hash = Column(String)  # just for simulation
    email = Column(String)

# For course files, we don't need a table – just filesystem.

Base.metadata.create_all(bind=engine)

def get_db_session():
    return SessionLocal()

# Helpers
def get_student_progress_db(student_id: str):
    session = get_db_session()
    try:
        results = session.query(ExamResult).filter_by(student_id=student_id).all()
        return [
            {"course_id": r.course_id, "term": r.term, "score": r.score, "feedback": r.feedback}
            for r in results
        ]
    finally:
        session.close()

def set_term_lock(term_name: str, locked: bool):
    session = get_db_session()
    try:
        term = session.query(Term).filter_by(name=term_name).first()
        if not term:
            term = Term(name=term_name, locked=locked)
            session.add(term)
        else:
            term.locked = locked
        session.commit()
    finally:
        session.close()

def get_term_info():
    session = get_db_session()
    try:
        terms = session.query(Term).all()
        return {t.name: {"locked": t.locked, "start": str(t.start_date), "end": str(t.end_date)} for t in terms}
    finally:
        session.close()
