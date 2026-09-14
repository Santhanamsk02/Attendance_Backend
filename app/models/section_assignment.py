import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, func, UniqueConstraint, ForeignKey
from sqlalchemy.orm import relationship
from app.database.database import Base


class SectionSubjectAssignment(Base):
    """
    Stores which teacher is responsible for a given subject within a
    specific section / academic context.  This is the canonical 'class teacher
    roster' that drives the timetable builder and attendance attribution.

    Unique per: (department_id, batch_id, semester, section_id, subject_id)
    """
    __tablename__ = "section_subject_assignments"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True, index=True)
    batch_id      = Column(String(36), ForeignKey("batches.id"),      nullable=True, index=True)
    academic_year_id = Column(Integer, ForeignKey("academic_years.id"), nullable=True, index=True)
    semester      = Column(Integer,    nullable=True, index=True)
    section_id    = Column(String(10), ForeignKey("sections.id"), nullable=True, index=True)

    subject_id    = Column(String(36), ForeignKey("subjects.id"), nullable=False, index=True)
    teacher_id    = Column(String(36), ForeignKey("teachers.id"), nullable=False)

    # Relationships
    department = relationship("Department")
    batch      = relationship("Batch")
    subject    = relationship("Subject")
    teacher    = relationship("Teacher")

    __table_args__ = (
        UniqueConstraint(
            "department_id", "batch_id", "semester", "section_id", "subject_id",
            name="uq_section_subject_assignment"
        ),
    )
