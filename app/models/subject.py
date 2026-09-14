import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, func, Index, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from app.database.database import Base


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    subject_code = Column(
        String(20),
        nullable=False,
        index=True,
    )
    subject_name = Column(
        String(200),
        nullable=False,
        index=True,
    )
    subject_title = Column(
        String(255),
        nullable=True,
    )
    department_id = Column(
        String(36),
        ForeignKey("departments.id"),
        nullable=False,
        index=True,
    )
    academic_year = Column(
        String(20),
        nullable=False,
        index=True,
    )
    semester = Column(
        Integer,
        nullable=False,
        index=True,
    )
    subject_type = Column(
        String(30),
        nullable=False,
        index=True,
    )
    credits = Column(
        Integer,
        nullable=True,
    )
    status = Column(
        String(10),
        nullable=False,
        default="active",
        index=True,
    )
    description = Column(
        Text,
        nullable=True,
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
    department_rel = relationship("Department", back_populates="subjects")

    __table_args__ = (
        UniqueConstraint(
            "subject_code", "department_id", "academic_year", "semester",
            name="uq_subject_context",
        ),
    )

    def __repr__(self):
        return f"<Subject {self.subject_code} - {self.subject_name}>"
