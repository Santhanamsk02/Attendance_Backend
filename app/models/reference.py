from sqlalchemy import Column, String, Integer, Date, DateTime, func
from app.database.database import Base


class Semester(Base):
    __tablename__ = "semesters"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)


class Section(Base):
    __tablename__ = "sections"
    id = Column(String(10), primary_key=True)
    name = Column(String(50), nullable=False)


class AcademicYear(Base):
    __tablename__ = "academic_years"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_current = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default='ACTIVE')
    created_at = Column(DateTime, default=func.now())
