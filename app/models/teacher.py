import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, func, Index, ForeignKey
from sqlalchemy.orm import relationship
from app.database.database import Base


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    employee_id = Column(
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
    designation = Column(
        String(100),
        nullable=True,
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
    department_rel = relationship("Department", back_populates="teachers")

    def __repr__(self):
        return f"<Teacher {self.employee_id} - {self.name}>"
