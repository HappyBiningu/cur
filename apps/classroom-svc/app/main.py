import os
import uuid
import random
import string
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, String, create_engine, select, UniqueConstraint
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# Config
JWT_SECRET = os.getenv("JWT_SECRET", "change_me")
JWT_ALGORITHM = "HS256"

DATABASE_URL = os.getenv("POSTGRES_URL")
if not DATABASE_URL:
    os.makedirs("/workspace/tmp", exist_ok=True)
    DATABASE_URL = "sqlite:////workspace/tmp/classroom.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class Class(Base):
    __tablename__ = "classes"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, nullable=False)
    lecturer_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    course_code = Column(String, nullable=True)
    description = Column(String, nullable=True)
    year = Column(String, nullable=True)
    class_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    enrollments = relationship("Enrollment", back_populates="clazz", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "class_id", name="uq_tenant_classid"),
    )

class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, nullable=False)
    class_id_fk = Column(String, ForeignKey("classes.id"), nullable=False)
    user_id = Column(String, nullable=False)
    role_in_class = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    clazz = relationship("Class", back_populates="enrollments")

    __table_args__ = (
        UniqueConstraint("tenant_id", "class_id_fk", "user_id", name="uq_enrollment"),
    )

# Schemas
class ClassCreate(BaseModel):
    name: str
    course_code: Optional[str] = None
    description: Optional[str] = None
    year: Optional[str] = None

class ClassOut(BaseModel):
    id: str
    tenant_id: str
    lecturer_id: str
    name: str
    course_code: Optional[str] = None
    description: Optional[str] = None
    year: Optional[str] = None
    class_id: str

    class Config:
        from_attributes = True

class JoinByCodeRequest(BaseModel):
    class_id: str

class EnrollmentOut(BaseModel):
    id: str
    tenant_id: str
    class_id_fk: str
    user_id: str
    role_in_class: str

    class Config:
        from_attributes = True

# FastAPI
app = FastAPI(title="classroom-svc")

# DB dep

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Auth dep

def get_current_user(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload  # contains sub, tenant_id, role
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Helpers

def generate_class_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))

# Startup
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

# Health
@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/readyz")
def readyz():
    return {"status": "ready"}

@app.get("/")
def root():
    return {"service": "classroom-svc"}

# Endpoints
@app.post("/classes", response_model=ClassOut)
def create_class(payload: ClassCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if user.get("role") not in ("Lecturer", "TenantAdmin", "PlatformAdmin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    class_code = generate_class_code()
    clazz = Class(
        tenant_id=user["tenant_id"],
        lecturer_id=user["sub"],
        name=payload.name,
        course_code=payload.course_code,
        description=payload.description,
        year=payload.year,
        class_id=class_code,
    )
    db.add(clazz)
    # Auto-enroll lecturer
    db.flush()
    enrollment = Enrollment(
        tenant_id=user["tenant_id"],
        class_id_fk=clazz.id,
        user_id=user["sub"],
        role_in_class="Lecturer",
    )
    db.add(enrollment)
    db.commit()
    db.refresh(clazz)
    return clazz

@app.get("/classes", response_model=List[ClassOut])
def list_classes(mine: bool = Query(False), user=Depends(get_current_user), db: Session = Depends(get_db)):
    if mine:
        stmt = (
            select(Class)
            .join(Enrollment, Enrollment.class_id_fk == Class.id)
            .where(
                Class.tenant_id == user["tenant_id"],
                Enrollment.user_id == user["sub"],
            )
        )
    else:
        stmt = select(Class).where(Class.tenant_id == user["tenant_id"])  # tenant-wide
    rows = db.execute(stmt).scalars().all()
    return rows

@app.post("/classes/join-by-code", response_model=EnrollmentOut)
def join_by_code(body: JoinByCodeRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    clazz = db.execute(
        select(Class).where(Class.class_id == body.class_id, Class.tenant_id == user["tenant_id"])  # tenant scoped
    ).scalar_one_or_none()
    if clazz is None:
        raise HTTPException(status_code=404, detail="Class not found")
    existing = db.execute(
        select(Enrollment).where(
            Enrollment.tenant_id == user["tenant_id"],
            Enrollment.class_id_fk == clazz.id,
            Enrollment.user_id == user["sub"],
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    enrollment = Enrollment(
        tenant_id=user["tenant_id"],
        class_id_fk=clazz.id,
        user_id=user["sub"],
        role_in_class="Student",
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment