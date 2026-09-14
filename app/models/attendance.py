from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Boolean, Date, Enum, Time, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database.database import Base

class SessionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"

class ScanMethod(str, enum.Enum):
    BARCODE_SCAN = "BARCODE_SCAN"
    MANUAL_ENTRY = "MANUAL_ENTRY"

class MarkStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LEAVE = "LEAVE"
    OD = "OD"
    HALF_DAY = "HALF_DAY"

class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    teacher_id = Column(String, ForeignKey("teachers.id"), index=True, nullable=False)
    subject_id = Column(String, ForeignKey("subjects.id"), index=True, nullable=True)
    department_id = Column(String, ForeignKey("departments.id"), nullable=True)
    batch_id = Column(String, ForeignKey("batches.id"), nullable=True)
    academic_year_id = Column(Integer, ForeignKey("academic_years.id"), nullable=True)
    semester = Column(Integer, nullable=True)
    section_id = Column(String, ForeignKey("sections.id"), nullable=True)
    
    date = Column(Date, nullable=False)
    period_id = Column(String, nullable=False)
    
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    room = Column(String(50), nullable=True)
    
    status = Column(Enum(SessionStatus), default=SessionStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    teacher = relationship("Teacher", backref="attendance_sessions")
    marks = relationship("AttendanceMark", back_populates="session", cascade="all, delete-orphan")


class AttendanceMark(Base):
    __tablename__ = "attendance_marks"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("attendance_sessions.id"), index=True, nullable=False)
    student_id = Column(String, ForeignKey("students.id"), index=True, nullable=False)
    
    roll_number = Column(String, nullable=True)
    status = Column(Enum(MarkStatus), default=MarkStatus.PRESENT)
    method = Column(Enum(ScanMethod), nullable=True)
    
    remarks = Column(Text, nullable=True)
    marked_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("AttendanceSession", back_populates="marks")
    student = relationship("Student", backref="attendance_marks")
