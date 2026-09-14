import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, func, Index, ForeignKey
from sqlalchemy.orm import relationship
from app.database.database import Base


class Student(Base):
    __tablename__ = "students"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    roll_no = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    name = Column(
        String(150),
        nullable=False,
        index=True,
    )
    email = Column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )
    phone = Column(
        String(30),
        nullable=True,
    )
    department_id = Column(
        String(36),
        ForeignKey("departments.id"),
        nullable=False,
        index=True,
    )
    batch_id = Column(
        String(36),
        ForeignKey("batches.id"),
        nullable=False,
        index=True,
    )
    semester = Column(
        Integer,
        ForeignKey("semesters.id"),
        nullable=False,
        index=True,
    )
    section = Column(
        String(10),
        ForeignKey("sections.id"),
        nullable=False,
        index=True,
    )
    academic_year = Column(
        String(20),
        nullable=False,
        index=True,
    )
    status = Column(
        String(20),
        nullable=False,
        default="active",
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    department_rel = relationship("Department", back_populates="students")
    batch_rel = relationship("Batch", back_populates="students")
    enrollments = relationship("StudentEnrollment", back_populates="student", order_by="desc(StudentEnrollment.created_at)")
    
    __table_args__ = (
        Index("ix_students_dept_sem_sec", "department_id", "semester", "section"),
    )

    def __repr__(self):
        return f"<Student {self.roll_no} - {self.name}>"

class StudentEnrollment(Base):
    __tablename__ = "student_enrollments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(36), ForeignKey("students.id"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=False)
    batch_id = Column(String(36), ForeignKey("batches.id"), nullable=True)
    academic_year_id = Column(Integer, ForeignKey("academic_years.id"), nullable=False)
    year = Column(Integer, nullable=True)
    semester = Column(Integer, nullable=False)
    section_id = Column(String(10), ForeignKey("sections.id"), nullable=True)
    
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default='ACTIVE')
    created_at = Column(DateTime, default=func.now())
    
    student = relationship("Student", back_populates="enrollments")

