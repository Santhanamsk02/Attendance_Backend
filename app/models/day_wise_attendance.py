from sqlalchemy import Column, String, ForeignKey, Date, Enum, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database.database import Base
from app.models.attendance import MarkStatus

class ScanMethod(str, enum.Enum):
    BARCODE_SCAN = "BARCODE_SCAN"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    AUTO_ROLLUP = "AUTO_ROLLUP"

class DayWiseAttendance(Base):
    __tablename__ = "day_wise_attendance"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    student_id = Column(String, ForeignKey("students.id"), index=True, nullable=False)
    date = Column(Date, nullable=False, index=True)
    status = Column(Enum(MarkStatus), default=MarkStatus.PRESENT)
    method = Column(Enum(ScanMethod), nullable=True)
    
    marked_by = Column(String, ForeignKey("teachers.id"), nullable=True)
    marked_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", backref="day_wise_records")
    teacher = relationship("Teacher", backref="day_wise_marks_given")
