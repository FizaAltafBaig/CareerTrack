from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./careertrack.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ---------------------------------------------------------------------------
# Models  (NOTE: __tablename__ needs TWO underscores on each side)
# ---------------------------------------------------------------------------
class Academy(Base):
    __tablename__ = "academies"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True)
    name = Column(String)
    accent_color = Column(String, default="#7c3aed")

    topics = relationship("CourseTopic", back_populates="academy")
    students = relationship("StudentProgress", back_populates="academy")


class CourseTopic(Base):
    __tablename__ = "course_topics"

    id = Column(Integer, primary_key=True, index=True)
    academy_slug = Column(String, ForeignKey("academies.slug"))
    role = Column(String, default="ML Engineer")
    title = Column(String)

    academy = relationship("Academy", back_populates="topics")


class StudentProgress(Base):
    __tablename__ = "student_progress"

    id = Column(Integer, primary_key=True, index=True)
    academy_slug = Column(String, ForeignKey("academies.slug"))
    student_name = Column(String)
    student_email = Column(String, index=True)
    target_role = Column(String, default="ML Engineer")
    course_progress = Column(Float, default=0.0)
    skills_verified = Column(Integer, default=0)
    projects_done = Column(Integer, default=0)
    readiness_score = Column(Float, default=0.0)
    at_risk = Column(Boolean, default=False)

    academy = relationship("Academy", back_populates="students")


Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# Seed demo data on startup
# ---------------------------------------------------------------------------
def seed_default_data():
    db = SessionLocal()
    try:
        if not db.query(Academy).filter_by(slug="default").first():
            db.add(Academy(slug="default", name="CareerTrack SaaS", accent_color="#7c3aed"))
            db.add_all([
                CourseTopic(academy_slug="default", role="ML Engineer",
                            title="Heart Disease Classification & ROC-AUC"),
                CourseTopic(academy_slug="default", role="Data Analyst",
                            title="Car Price Prediction & Feature Regression"),
                CourseTopic(academy_slug="default", role="LLM / Agent Developer",
                            title="Bank Fraud Detection & Anomaly Scoring"),
            ])
            db.add_all([
                StudentProgress(
                    academy_slug="default", student_name="Ayesha Khan", student_email="ayesha@example.com",
                    target_role="ML Engineer", course_progress=85.0, skills_verified=24,
                    projects_done=3, readiness_score=82.5, at_risk=False,
                ),
                StudentProgress(
                    academy_slug="default", student_name="Bilal Ahmed", student_email="bilal@example.com",
                    target_role="Data Analyst", course_progress=25.0, skills_verified=6,
                    projects_done=1, readiness_score=28.5, at_risk=True,
                ),
            ])
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_default_data()
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="CareerTrack SaaS API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AcademyCreate(BaseModel):
    slug: str
    name: str
    accent_color: str = "#7c3aed"


class TopicCreate(BaseModel):
    academy_slug: str = "default"
    role: str = "ML Engineer"
    title: str


class ProgressUpdate(BaseModel):
    academy_slug: str = "default"
    student_name: str
    student_email: str
    target_role: str = "ML Engineer"
    course_progress: float = 0.0
    skills_verified: int = 0
    projects_done: int = 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def health():
    return {"status": "ok", "service": "CareerTrack SaaS API"}


@app.post("/academies")
def create_or_update_academy(payload: AcademyCreate):
    db = SessionLocal()
    try:
        acad = db.query(Academy).filter_by(slug=payload.slug).first()
        if acad:
            acad.name = payload.name
            acad.accent_color = payload.accent_color
        else:
            acad = Academy(slug=payload.slug, name=payload.name, accent_color=payload.accent_color)
            db.add(acad)
        db.commit()
        db.refresh(acad)
        return {"id": acad.id, "slug": acad.slug, "name": acad.name, "accent_color": acad.accent_color}
    finally:
        db.close()


@app.get("/academies/{slug}")
def get_academy(slug: str):
    db = SessionLocal()
    try:
        acad = db.query(Academy).filter_by(slug=slug).first()
        if not acad:
            raise HTTPException(status_code=404, detail="Academy not found")
        topics = db.query(CourseTopic).filter_by(academy_slug=slug).all()
        return {
            "slug": acad.slug,
            "name": acad.name,
            "accent_color": acad.accent_color,
            "topics": [{"id": t.id, "role": t.role, "title": t.title} for t in topics],
        }
    finally:
        db.close()


@app.post("/topics")
def add_topic(payload: TopicCreate):
    db = SessionLocal()
    try:
        if not db.query(Academy).filter_by(slug=payload.academy_slug).first():
            db.add(Academy(slug=payload.academy_slug, name=payload.academy_slug.title()))
            db.commit()
        topic = CourseTopic(academy_slug=payload.academy_slug, role=payload.role, title=payload.title)
        db.add(topic)
        db.commit()
        db.refresh(topic)
        return {"id": topic.id, "academy_slug": topic.academy_slug, "role": topic.role, "title": topic.title}
    finally:
        db.close()


@app.post("/progress")
def upsert_progress(payload: ProgressUpdate):
    db = SessionLocal()
    try:
        if not db.query(Academy).filter_by(slug=payload.academy_slug).first():
            db.add(Academy(slug=payload.academy_slug, name=payload.academy_slug.title()))
            db.commit()

        readiness = round(
            min(
                100.0,
                payload.course_progress * 0.5
                + (payload.skills_verified / 30) * 30
                + (payload.projects_done / 4) * 20,
            ),
            1,
        )
        at_risk = readiness < 45.0

        row = (
            db.query(StudentProgress)
            .filter_by(academy_slug=payload.academy_slug, student_email=payload.student_email)
            .first()
        )
        if row:
            row.student_name = payload.student_name
            row.target_role = payload.target_role
            row.course_progress = payload.course_progress
            row.skills_verified = payload.skills_verified
            row.projects_done = payload.projects_done
            row.readiness_score = readiness
            row.at_risk = at_risk
        else:
            row = StudentProgress(
                academy_slug=payload.academy_slug,
                student_name=payload.student_name,
                student_email=payload.student_email,
                target_role=payload.target_role,
                course_progress=payload.course_progress,
                skills_verified=payload.skills_verified,
                projects_done=payload.projects_done,
                readiness_score=readiness,
                at_risk=at_risk,
            )
            db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "id": row.id,
            "student_name": row.student_name,
            "readiness_score": row.readiness_score,
            "at_risk": row.at_risk,
        }
    finally:
        db.close()


@app.get("/cohort/{academy_slug}")
def cohort_summary(academy_slug: str):
    db = SessionLocal()
    try:
        students = db.query(StudentProgress).filter_by(academy_slug=academy_slug).all()
        topics = db.query(CourseTopic).filter_by(academy_slug=academy_slug).all()
        total = len(students)
        avg_readiness = round(sum(s.readiness_score for s in students) / total, 1) if total else 0.0
        at_risk_count = sum(1 for s in students if s.at_risk)
        interview_ready = sum(1 for s in students if s.readiness_score >= 70.0)
        return {
            "academy_slug": academy_slug,
            "total_students": total,
            "interview_ready": interview_ready,
            "at_risk_students": at_risk_count,
            "avg_readiness": avg_readiness,
            "topics": [{"id": t.id, "role": t.role, "title": t.title} for t in topics],
            "students": [
                {
                    "name": s.student_name,
                    "email": s.student_email,
                    "role": s.target_role,
                    "course_progress": s.course_progress,
                    "skills_verified": s.skills_verified,
                    "projects_done": s.projects_done,
                    "readiness_score": s.readiness_score,
                    "at_risk": s.at_risk,
                }
                for s in students
            ],
        }
    finally:
        db.close()