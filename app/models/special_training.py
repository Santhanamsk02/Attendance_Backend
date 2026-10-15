import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Date, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.database.database import Base

class SpecialTraining(Base):
    __tablename__ = "special_trainings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    name = Column(String(150), nullable=False, index=True)
    batch_id = Column(String(36), ForeignKey("batches.id", ondelete="SET NULL"), nullable=True, index=True)
    batch_name = Column(String(50), nullable=False, index=True)
    trainer_name = Column(String(100), nullable=True)
    trainer_organization = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    venue = Column(String(100), nullable=True)
    timeline_config = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    batch = relationship("Batch", backref="special_trainings")
    subjects = relationship("SpecialTrainingSubject", back_populates="training", cascade="all, delete-orphan", passive_deletes=True)
    enrollments = relationship("SpecialTrainingEnrollment", back_populates="training", cascade="all, delete-orphan", passive_deletes=True)
    timetable_slots = relationship("SpecialTrainingTimetable", back_populates="training", cascade="all, delete-orphan", passive_deletes=True)
    staff_assignments = relationship("SpecialTrainingStaffAssignment", back_populates="training", cascade="all, delete-orphan", passive_deletes=True)
    sessions = relationship("SpecialTrainingSession", back_populates="training", cascade="all, delete-orphan", passive_deletes=True)


class SpecialTrainingSubject(Base):
    """
    Subjects / modules configured specifically for a Special Training program.
    Persisted in DB and scheduled across timetable slots.
    """
    __tablename__ = "special_training_subjects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    training_id = Column(String(36), ForeignKey("special_trainings.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    code = Column(String(50), nullable=True)
    trainer_name = Column(String(100), nullable=True)
    venue = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    training = relationship("SpecialTraining", back_populates="subjects")


class SpecialTrainingEnrollment(Base):
    """
    Students enrolled in the training from multiple departments.
    """
    __tablename__ = "special_training_enrollments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    training_id = Column(String(36), ForeignKey("special_trainings.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    enrolled_at = Column(DateTime, server_default=func.now(), nullable=False)

    training = relationship("SpecialTraining", back_populates="enrollments")
    student = relationship("Student", backref="special_training_enrollments")

    __table_args__ = (
        UniqueConstraint("training_id", "student_id", name="uq_special_training_student"),
    )


class SpecialTrainingTimetable(Base):
    """
    Timetable slots defined for the special training (shared across all departments).
    Trainer takes the class here.
    """
    __tablename__ = "special_training_timetables"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    training_id = Column(String(36), ForeignKey("special_trainings.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(String(20), nullable=False, index=True) # MON, TUE, WED, THU, FRI, SAT
    period_id = Column(String(20), nullable=False, index=True)   # P1, P2, etc.
    start_time = Column(String(10), nullable=True)               # e.g., "09:00"
    end_time = Column(String(10), nullable=True)                 # e.g., "10:30"
    topic = Column(String(150), nullable=True)                  # e.g., "Full Stack Module 1"
    trainer_name = Column(String(100), nullable=True)           # e.g., "Mr. John Doe"
    venue = Column(String(100), nullable=True)                  # e.g., "Auditorium"
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    training = relationship("SpecialTraining", back_populates="timetable_slots")

    __table_args__ = (
        UniqueConstraint("training_id", "day_of_week", "period_id", name="uq_special_training_slot"),
    )


class SpecialTrainingStaffAssignment(Base):
    """
    Assigns one or multiple teachers (staff) to a training slot to take attendance.
    """
    __tablename__ = "special_training_staff_assignments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    training_id = Column(String(36), ForeignKey("special_trainings.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(String(20), nullable=False, index=True)
    period_id = Column(String(20), nullable=False, index=True)
    teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    training = relationship("SpecialTraining", back_populates="staff_assignments")
    teacher = relationship("Teacher", backref="special_training_assignments")

    __table_args__ = (
        UniqueConstraint("training_id", "day_of_week", "period_id", "teacher_id", name="uq_special_training_staff"),
    )


class SpecialTrainingSession(Base):
    """
    Instance of a training class on a specific calendar date and period.
    """
    __tablename__ = "special_training_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    training_id = Column(String(36), ForeignKey("special_trainings.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    period_id = Column(String(20), nullable=False, index=True)
    status = Column(String(20), default="ACTIVE") # ACTIVE, COMPLETED
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    training = relationship("SpecialTraining", back_populates="sessions")
    marks = relationship("SpecialTrainingMark", back_populates="session", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        UniqueConstraint("training_id", "date", "period_id", name="uq_special_training_session"),
    )


class SpecialTrainingMark(Base):
    """
    Student attendance mark in a special training session.
    Records marked_by_teacher_id to support concurrent marking by multiple teachers.
    """
    __tablename__ = "special_training_marks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    session_id = Column(String(36), ForeignKey("special_training_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default="PRESENT") # PRESENT, ABSENT
    marked_by_teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    method = Column(String(30), default="MANUAL_ENTRY") # BARCODE_SCAN, MANUAL_ENTRY
    marked_at = Column(DateTime, server_default=func.now(), nullable=False)

    session = relationship("SpecialTrainingSession", back_populates="marks")
    student = relationship("Student")
    marked_by = relationship("Teacher")

    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_special_training_mark"),
    )
