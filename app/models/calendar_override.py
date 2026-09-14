import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, func, ForeignKey, Integer, JSON
from app.database.database import Base

class CalendarOverride(Base):
    """
    Stores single-day or multi-day date range timetable/calendar overrides.
    Supported types:
    - HOLIDAY: Full day holiday
    - HALF_DAY: Morning/Afternoon half day
    - SUBSTITUTE_STAFF: Assign substitute teacher for period(s)
    - CHANGE_PERIOD: Change/swap assigned subject or teacher for period(s)
    - ADD_PERIOD: Add extra period(s)
    - CHANGE_TIMINGS: Custom bell schedule timings for the day
    - EXAM_DAY: Special exam timetable schedule
    - EVENT_DAY: Special activity / event day schedule
    - DAY_SWAP: Operate day on another weekday's timetable
    """
    __tablename__ = "calendar_overrides"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    title = Column(String(150), nullable=False)
    override_type = Column(String(50), nullable=False, index=True)
    
    start_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    end_date = Column(String(10), nullable=False, index=True)    # YYYY-MM-DD
    
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True, index=True)
    batch_id = Column(String(36), ForeignKey("batches.id"), nullable=True)
    academic_year = Column(String(20), nullable=True)
    semester = Column(Integer, nullable=True)
    section_name = Column(String(100), nullable=True)
    
    details = Column(JSON, nullable=False, default=dict)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
