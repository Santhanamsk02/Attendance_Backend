from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.database.database import get_db
from app.models.calendar_override import CalendarOverride
from app.models.timetable import TeacherAssignment
from app.models.teacher import Teacher
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

router = APIRouter(prefix="/calendar/overrides", tags=["Calendar Overrides"])

class CalendarOverrideCreate(BaseModel):
    title: str
    override_type: str
    start_date: str
    end_date: str
    department_id: Optional[str] = None
    batch_id: Optional[str] = None
    academic_year: Optional[str] = None
    semester: Optional[int] = None
    section_name: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

class CalendarOverrideUpdate(BaseModel):
    title: Optional[str] = None
    override_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    department_id: Optional[str] = None
    batch_id: Optional[str] = None
    academic_year: Optional[str] = None
    semester: Optional[int] = None
    section_name: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

def _validate_teacher_availability(db: Session, start_date: str, override_type: str, details: dict):
    if override_type not in ["SUBSTITUTE_STAFF", "CHANGE_PERIOD"]:
        return

    try:
        date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        day_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        day_code = day_map[date_obj.weekday()]
        if day_code == "SUN":
            day_code = "MON"
            
        assignments_to_check = []
        
        # Format 1: details.periodOverrides = { "period-1": { "teacher_id": ... } }
        if "periodOverrides" in details:
            for pid, p_details in details["periodOverrides"].items():
                t_id = p_details.get("teacher_id") or p_details.get("teacher")
                if t_id:
                    assignments_to_check.append((pid, t_id))
                    
        # Format 2: details = { "periodId": "period-1", "substituteTeacherId": ... }
        if "periodId" in details:
            t_id = details.get("substituteTeacherId") or details.get("newTeacherId")
            if t_id:
                assignments_to_check.append((details["periodId"], t_id))
                
        for pid, t_id in assignments_to_check:
            conflict = db.query(TeacherAssignment).filter(
                TeacherAssignment.teacher_id == t_id,
                TeacherAssignment.day_of_week == day_code,
                TeacherAssignment.period_id == pid
            ).first()
            
            if conflict:
                teacher = db.query(Teacher).filter(Teacher.id == t_id).first()
                t_name = teacher.name if teacher else "Unknown"
                raise HTTPException(
                    status_code=400, 
                    detail=f"Teacher {t_name} is already assigned to a class on {day_code} at {pid}. Please select a different teacher or period."
                )
    except ValueError:
        pass # Invalid date string

@router.get("")
@router.get("/")
def get_calendar_overrides(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    department_id: Optional[str] = Query(None),
    override_type: Optional[str] = Query(None),
    academic_year: Optional[str] = Query(None),
    semester: Optional[int] = Query(None),
    section_name: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):

    query = db.query(CalendarOverride)
    
    if start_date and end_date:
        # Overrides that overlap with the queried date range
        query = query.filter(
            and_(
                CalendarOverride.start_date <= end_date,
                CalendarOverride.end_date >= start_date
            )
        )
    elif start_date:
        query = query.filter(CalendarOverride.end_date >= start_date)
    elif end_date:
        query = query.filter(CalendarOverride.start_date <= end_date)

    if override_type:
        query = query.filter(CalendarOverride.override_type == override_type)
        
    if department_id:
        query = query.filter(
            or_(
                CalendarOverride.department_id == department_id,
                CalendarOverride.department_id.is_(None)
            )
        )
        
    if academic_year:
        query = query.filter(
            or_(
                CalendarOverride.academic_year == academic_year,
                CalendarOverride.academic_year.is_(None)
            )
        )

    if semester is not None:
        query = query.filter(
            or_(
                CalendarOverride.semester == semester,
                CalendarOverride.semester.is_(None)
            )
        )

    if section_name:
        query = query.filter(
            or_(
                CalendarOverride.section_name == section_name,
                CalendarOverride.section_name.is_(None)
            )
        )

    overrides = query.order_by(CalendarOverride.start_date.asc()).all()
    
    items = []
    for item in overrides:
        items.append({
            "id": item.id,
            "title": item.title,
            "override_type": item.override_type,
            "start_date": item.start_date,
            "end_date": item.end_date,
            "department_id": item.department_id,
            "batch_id": item.batch_id,
            "academic_year": item.academic_year,
            "semester": item.semester,
            "section_name": item.section_name,
            "details": item.details,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        })
        
    return {"status": "success", "count": len(items), "items": items}

@router.get("/{override_id}")
def get_calendar_override(override_id: str, db: Session = Depends(get_db)):
    override = db.query(CalendarOverride).filter(CalendarOverride.id == override_id).first()
    if not override:
        raise HTTPException(status_code=404, detail="Calendar override not found")
        
    return {
        "id": override.id,
        "title": override.title,
        "override_type": override.override_type,
        "start_date": override.start_date,
        "end_date": override.end_date,
        "department_id": override.department_id,
        "batch_id": override.batch_id,
        "academic_year": override.academic_year,
        "semester": override.semester,
        "section_name": override.section_name,
        "details": override.details,
        "created_at": override.created_at.isoformat() if override.created_at else None,
        "updated_at": override.updated_at.isoformat() if override.updated_at else None,
    }

@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_calendar_override(payload: CalendarOverrideCreate, db: Session = Depends(get_db)):

    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date cannot be earlier than start_date")

    _validate_teacher_availability(db, payload.start_date, payload.override_type, payload.details)

    override = CalendarOverride(
        title=payload.title,
        override_type=payload.override_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        department_id=payload.department_id,
        batch_id=payload.batch_id,
        academic_year=payload.academic_year,
        semester=payload.semester,
        section_name=payload.section_name,
        details=payload.details
    )
    
    db.add(override)
    db.commit()
    db.refresh(override)
    
    return {
        "status": "success",
        "message": "Calendar override created successfully",
        "item": {
            "id": override.id,
            "title": override.title,
            "override_type": override.override_type,
            "start_date": override.start_date,
            "end_date": override.end_date,
            "department_id": override.department_id,
            "batch_id": override.batch_id,
            "academic_year": override.academic_year,
            "semester": override.semester,
            "section_name": override.section_name,
            "details": override.details,
            "created_at": override.created_at.isoformat() if override.created_at else None,
        }
    }

@router.put("/{override_id}")
def update_calendar_override(override_id: str, payload: CalendarOverrideUpdate, db: Session = Depends(get_db)):
    override = db.query(CalendarOverride).filter(CalendarOverride.id == override_id).first()
    if not override:
        raise HTTPException(status_code=404, detail="Calendar override not found")

    update_data = payload.dict(exclude_unset=True)
    
    if "start_date" in update_data or "end_date" in update_data:
        new_start = update_data.get("start_date", override.start_date)
        new_end = update_data.get("end_date", override.end_date)
        if new_end < new_start:
            raise HTTPException(status_code=400, detail="end_date cannot be earlier than start_date")

    override_type = update_data.get("override_type", override.override_type)
    start_date = update_data.get("start_date", override.start_date)
    details = update_data.get("details", override.details)
    _validate_teacher_availability(db, start_date, override_type, details)

    for key, value in update_data.items():
        setattr(override, key, value)
        
    db.commit()
    db.refresh(override)

    return {
        "status": "success",
        "message": "Calendar override updated successfully",
        "item": {
            "id": override.id,
            "title": override.title,
            "override_type": override.override_type,
            "start_date": override.start_date,
            "end_date": override.end_date,
            "department_id": override.department_id,
            "batch_id": override.batch_id,
            "academic_year": override.academic_year,
            "semester": override.semester,
            "section_name": override.section_name,
            "details": override.details,
            "updated_at": override.updated_at.isoformat() if override.updated_at else None,
        }
    }

@router.delete("/{override_id}")
def delete_calendar_override(override_id: str, db: Session = Depends(get_db)):
    override = db.query(CalendarOverride).filter(CalendarOverride.id == override_id).first()
    if not override:
        raise HTTPException(status_code=404, detail="Calendar override not found")
        
    db.delete(override)
    db.commit()
    
    return {"status": "success", "message": "Calendar override deleted successfully"}
