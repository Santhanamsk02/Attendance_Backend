from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.database.database import Base
import uuid

class Batch(Base):
    __tablename__ = "batches"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    batch_name = Column(String, nullable=False) # e.g., "2023-2027"
    current_year = Column(Integer, nullable=False) # e.g., 2
    current_semester = Column(Integer, nullable=False) # e.g., 4
    sections_count = Column(Integer, nullable=False, default=1) # e.g., 5 meaning A-E

    # Relationships
    department = relationship("Department", back_populates="batches")
    students = relationship("Student", back_populates="batch_rel")
