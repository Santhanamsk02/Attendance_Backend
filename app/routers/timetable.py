from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.timetable import TeacherAssignment, TimetableStructure
from app.models.subject import Subject
from app.models.department import Department
from app.models.batch import Batch
from app.models.teacher import Teacher
from app.models.reference import AcademicYear
from pydantic import BaseModel
from typing import Dict, Any, Optional
from collections import defaultdict

router = APIRouter(prefix="/timetable", tags=["Timetable"])

class TimetablePayload(BaseModel):
    department: str          # department code, e.g. "IT"
    academic_year: str
    semester: int
    section_name: str
    grid_data: Dict[str, Any]


def _resolve_dept(db: Session, department_code: str) -> Optional[Department]:
    """Resolve a department code like 'IT' to its Department ORM object."""
    return db.query(Department).filter(
        (Department.code == department_code) | (Department.id == department_code)
    ).first()


def _resolve_batch(db: Session, department_id: str, academic_year: str) -> Optional[Batch]:
    return db.query(Batch).filter(
        Batch.department_id == department_id,
        Batch.batch_name == academic_year
    ).first()


@router.get("/")
def get_timetable(
    department: str = Query(...),
    academic_year: str = Query(...),
    semester: int = Query(...),
    section_name: str = Query(...),
    db: Session = Depends(get_db)
):
    dept = _resolve_dept(db, department)
    if not dept:
        return {"exists": False, "grid_data": None}

    batch = _resolve_batch(db, dept.id, academic_year)
    if not batch:
        return {"exists": False, "grid_data": None}

    struct = db.query(TimetableStructure).filter(
        TimetableStructure.department_id == dept.id,
        TimetableStructure.batch_id == batch.id,
        TimetableStructure.academic_year == academic_year,
        TimetableStructure.semester == semester,
        TimetableStructure.section_name == section_name
    ).first()

    if not struct:
        return {"exists": False, "grid_data": None}

    return {"exists": True, "grid_data": struct.grid_data}


@router.post("/")
def save_timetable(
    payload: TimetablePayload,
    db: Session = Depends(get_db)
):
    dept = _resolve_dept(db, payload.department)
    if not dept:
        raise HTTPException(status_code=404, detail=f"Department '{payload.department}' not found")

    batch = _resolve_batch(db, dept.id, payload.academic_year)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Academic year '{payload.academic_year}' not found for this department")

    # 1. Upsert TimetableStructure
    struct = db.query(TimetableStructure).filter(
        TimetableStructure.department_id == dept.id,
        TimetableStructure.batch_id == batch.id,
        TimetableStructure.academic_year == payload.academic_year,
        TimetableStructure.semester == payload.semester,
        TimetableStructure.section_name == payload.section_name
    ).first()

    if struct:
        struct.grid_data = payload.grid_data
    else:
        struct = TimetableStructure(
            department_id=dept.id,
            batch_id=batch.id,
            academic_year=payload.academic_year,
            semester=payload.semester,
            section_name=payload.section_name,
            grid_data=payload.grid_data
        )
        db.add(struct)

    # 2. Sync Relational TeacherAssignments — wipe previous ones for this section context
    subjects = db.query(Subject.id, Subject.subject_code).filter(
        Subject.department_id == dept.id,
        Subject.academic_year == payload.academic_year,
        Subject.semester == payload.semester
    ).all()
    valid_subject_ids = [s[0] for s in subjects]
    subject_map = {s[1]: s[0] for s in subjects}

    if valid_subject_ids:
        db.query(TeacherAssignment).filter(
            TeacherAssignment.section_id == payload.section_name,
            TeacherAssignment.subject_id.in_(valid_subject_ids)
        ).delete(synchronize_session=False)

    # 3. Validation Rules
    days_data = payload.grid_data.get("days", [])
    
    involved_teachers = set()
    for d in days_data:
        for entry in d.get("entries", []):
            if entry.get("teacher_id"):
                involved_teachers.add(entry["teacher_id"])
                
    if involved_teachers:
        existing_assignments = db.query(TeacherAssignment).filter(
            TeacherAssignment.teacher_id.in_(involved_teachers)
        ).all()
        
        # Filter out the assignments about to be wiped from THIS section
        remaining = [a for a in existing_assignments if not (a.section_id == payload.section_name and a.subject_id in valid_subject_ids)]
        
        teacher_day_periods = defaultdict(lambda: defaultdict(list))
        teacher_day_counts = defaultdict(lambda: defaultdict(int))
        
        for a in remaining:
            teacher_day_periods[a.teacher_id][a.day_of_week].append(a.period_id)
            teacher_day_counts[a.teacher_id][a.day_of_week] += 1
            
        teacher_objects = db.query(Teacher.id, Teacher.name).filter(Teacher.id.in_(involved_teachers)).all()
        t_names = {t[0]: t[1] for t in teacher_objects}
        
        for d in days_data:
            day_value = d.get("day")
            for entry in d.get("entries", []):
                t_id = entry.get("teacher_id")
                if not t_id:
                    continue
                
                pid = entry.get("timeline_item_id") or entry.get("start_timeline_item_id")
                
                if pid in teacher_day_periods[t_id][day_value]:
                    t_name = t_names.get(t_id, "Unknown")
                    friendly_day = day_value.capitalize()
                    period_friendly = pid.replace("period-", "")
                    raise HTTPException(status_code=400, detail=f"Teacher {t_name} is already assigned to a class on {friendly_day} at Period {period_friendly}.")
                
                teacher_day_periods[t_id][day_value].append(pid)
                teacher_day_counts[t_id][day_value] += 1
                
                if teacher_day_counts[t_id][day_value] >= 8:
                    t_name = t_names.get(t_id, "Unknown")
                    raise HTTPException(status_code=400, detail=f"Teacher {t_name} exceeded the maximum limit of 7 classes per day.")

    # 4. Create fresh TeacherAssignment slots based on the Day grid
    ay = db.query(AcademicYear).filter(AcademicYear.name == payload.academic_year).first()
    ay_id = ay.id if ay else None

    for d in days_data:
        day_value = d.get("day")
        for entry in d.get("entries", []):
            if entry.get("subject_code") and entry.get("teacher_id"):
                subj_id = subject_map.get(entry["subject_code"])
                if not subj_id:
                    continue
                new_assignment = TeacherAssignment(
                    teacher_id=entry["teacher_id"],
                    subject_id=subj_id,
                    department_id=dept.id,
                    batch_id=batch.id,
                    academic_year_id=ay_id,
                    semester=payload.semester,
                    section_id=payload.section_name,
                    day_of_week=day_value,
                    period_id=entry.get("timeline_item_id") or entry.get("start_timeline_item_id"),
                    room=entry.get("room"),
                    type=entry.get("session_type", "theory"),
                    span=entry.get("span", 1)
                )
                db.add(new_assignment)

    db.commit()

    return {"status": "success", "message": "Timetable saved successfully"}


@router.get("/sections-status")
def get_sections_status(
    department: str = Query(...),
    academic_year: str = Query(...),
    semester: int = Query(...),
    db: Session = Depends(get_db)
):
    dept = _resolve_dept(db, department)
    if not dept:
        return {"configured_sections": []}

    assignments = db.query(TeacherAssignment.section_id).join(
        Subject, TeacherAssignment.subject_id == Subject.id
    ).filter(
        Subject.department_id == dept.id,
        Subject.academic_year == academic_year,
        Subject.semester == semester
    ).distinct().all()

    configured_sections = [a[0] for a in assignments]
    return {"configured_sections": configured_sections}
