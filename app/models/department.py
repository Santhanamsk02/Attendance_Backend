from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from app.database.database import Base
import uuid

class Department(Base):
    __tablename__ = "departments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True, index=True) # e.g., "Information Technology"
    code = Column(String, nullable=False, unique=True, index=True) # e.g., "IT"
    morning_entry_time = Column(String, nullable=True) # e.g., "07:00-08:00"

    # Relationships
    batches = relationship("Batch", back_populates="department")
    students = relationship("Student", back_populates="department_rel")
    teachers = relationship("Teacher", back_populates="department_rel")
    subjects = relationship("Subject", back_populates="department_rel")
