import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, func, Index, ForeignKey, Integer, JSON
from sqlalchemy.orm import relationship
from app.database.database import Base

class TeacherAssignment(Base):
    """
    Maps a Teacher to a Subject, Section, and Period on a specific Day.
    Forms the baseline weekly timetable layout.
    """
    __tablename__ = "teacher_assignments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    teacher_id = Column(String(36), ForeignKey("teachers.id"), nullable=False, index=True)
    subject_id = Column(String(36), ForeignKey("subjects.id"), nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True)
    batch_id = Column(String(36), ForeignKey("batches.id"), nullable=True)
    academic_year_id = Column(Integer, ForeignKey("academic_years.id"), nullable=True)
    semester = Column(Integer, nullable=True)
    section_id = Column(String(10), ForeignKey("sections.id"), nullable=True, index=True)
    
    day_of_week = Column(String(20), nullable=False, index=True)
    period_id = Column(String(20), nullable=False, index=True)
    room = Column(String(50), nullable=True)
    type = Column(String(20), default='theory')
    span = Column(Integer, default=1)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    teacher = relationship("Teacher", backref="assignments")

class TimetableStructure(Base):
    """
    Stores the exact structural layout of a Timetable (timeline, periods, days configuration)
    for a specific Department, Academic Year, Semester, and Section. 
    This acts as the source of truth for hydrating the frontend Admin Timetable Grid planner.
    """
    __tablename__ = "timetable_structures"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=False, index=True)
    batch_id = Column(String(36), ForeignKey("batches.id"), nullable=False, index=True)
    academic_year = Column(String(20), nullable=False, index=True)
    semester = Column(Integer, nullable=False, index=True)
    section_name = Column(String(100), nullable=False, index=True)
    
    grid_data = Column(JSON, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
