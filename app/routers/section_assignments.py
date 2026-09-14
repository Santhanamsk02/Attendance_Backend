from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from pydantic import BaseModel

from app.database.database import get_db
from app.models.section_assignment import SectionSubjectAssignment
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.department import Department
from app.models.batch import Batch
from app.models.timetable import TeacherAssignment

router = APIRouter(prefix="/section-assignments", tags=["Section Assignments"])


# ── Schemas ────────────────────────────────────────────────────────────────

class AssignmentUpsert(BaseModel):
    subject_id: str
    teacher_id: Optional[str] = None   # None means "unassign"


class BulkSaveRequest(BaseModel):
    department: str          # department code, e.g. "IT"
    academic_year: str
    semester: int
    section_name: str
    assignments: List[AssignmentUpsert]


class TeacherBrief(BaseModel):
    id: str
    name: str
    employee_id: str

    class Config:
        from_attributes = True


class SubjectBrief(BaseModel):
    id: str
    subject_code: str
    subject_name: str
    subject_title: Optional[str] = None
    subject_type: str
    credits: Optional[int] = None

    class Config:
        from_attributes = True


class AssignmentOut(BaseModel):
    id: str
    subject: SubjectBrief
    teacher: Optional[TeacherBrief] = None

    class Config:
        from_attributes = True


# ── Helpers ────────────────────────────────────────────────────────────────

def _resolve_dept(db: Session, code: str) -> Department:
    obj = db.query(Department).filter(Department.code == code).first()
    if not obj:
        raise HTTPException(status_code=404, detail=f"Department '{code}' not found")
    return obj


def _resolve_batch(db: Session, dept_id: str, academic_year: str) -> Batch:
    obj = db.query(Batch).filter(
        Batch.department_id == dept_id,
        Batch.batch_name == academic_year
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail=f"Batch '{academic_year}' not found for this department")
    return obj


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/")
def get_assignments(
    department: str = Query(...),
    academic_year: str = Query(...),
    semester: int = Query(...),
    section_name: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Returns the full assignment list for this section — all subjects + their assigned teacher (or null).
    """
    dept = _resolve_dept(db, department)
    batch = _resolve_batch(db, dept.id, academic_year)

    # All subjects for this context
    all_subjects = db.query(Subject).filter(
        Subject.department_id == dept.id,
        Subject.academic_year == academic_year,
        Subject.semester == semester,
        Subject.status == "active"
    ).order_by(Subject.subject_name).all()

    # Existing assignments for this section
    existing = {
        a.subject_id: a
        for a in db.query(SectionSubjectAssignment).filter(
            SectionSubjectAssignment.department_id == dept.id,
            SectionSubjectAssignment.batch_id == batch.id,
            SectionSubjectAssignment.semester == semester,
            SectionSubjectAssignment.section_id == section_name
        ).all()
    }

    result = []
    for subj in all_subjects:
        asgn = existing.get(subj.id)
        teacher_data = None
        if asgn and asgn.teacher_id:
            t = db.query(Teacher).filter(Teacher.id == asgn.teacher_id).first()
            if t:
                teacher_data = {"id": t.id, "name": t.name, "employee_id": t.employee_id}

        result.append({
            "subject": {
                "id": subj.id,
                "subject_code": subj.subject_code,
                "subject_name": subj.subject_name,
                "subject_title": subj.subject_title,
                "subject_type": subj.subject_type,
                "credits": subj.credits,
            },
            "teacher": teacher_data,
            "assignment_id": asgn.id if asgn else None,
        })

    return result


@router.post("/bulk-save")
def bulk_save_assignments(
    payload: BulkSaveRequest,
    db: Session = Depends(get_db)
):
    """
    Upserts a full list of subject→teacher assignments for a section.
    Supply teacher_id=null to remove the teacher from a subject.
    """
    dept = _resolve_dept(db, payload.department)
    batch = _resolve_batch(db, dept.id, payload.academic_year)

    upserted = 0
    for item in payload.assignments:
        existing = db.query(SectionSubjectAssignment).filter(
            SectionSubjectAssignment.department_id == dept.id,
            SectionSubjectAssignment.batch_id == batch.id,
            SectionSubjectAssignment.semester == payload.semester,
            SectionSubjectAssignment.section_id == payload.section_name,
            SectionSubjectAssignment.subject_id == item.subject_id
        ).first()

        if not item.teacher_id:
            if existing:
                db.delete(existing)
                # Remove teacher assignments from timetable
                db.query(TeacherAssignment).filter(
                    TeacherAssignment.section_id == payload.section_name,
                    TeacherAssignment.subject_id == item.subject_id
                ).delete(synchronize_session=False)
                upserted += 1
            continue

        if existing:
            existing.teacher_id = item.teacher_id
        else:
            db.add(SectionSubjectAssignment(
                department_id=dept.id,
                batch_id=batch.id,
                academic_year_id=batch.academic_year_id if hasattr(batch, 'academic_year_id') else None,
                semester=payload.semester,
                section_id=payload.section_name,
                subject_id=item.subject_id,
                teacher_id=item.teacher_id
            ))
            
        # Also sync to TeacherAssignment (timetable) table
        db.query(TeacherAssignment).filter(
            TeacherAssignment.section_id == payload.section_name,
            TeacherAssignment.subject_id == item.subject_id
        ).update({
            "teacher_id": item.teacher_id,
            "department_id": dept.id,
            "batch_id": batch.id
        }, synchronize_session=False)
        
        upserted += 1

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "success", "upserted": upserted}


@router.get("/teachers")
def get_department_teachers(
    department: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Returns all active teachers for a given department code.
    """
    dept = _resolve_dept(db, department)
    teachers = db.query(Teacher).filter(
        Teacher.department_id == dept.id,
        Teacher.status == "active"
    ).order_by(Teacher.name).all()

    return [{"id": t.id, "name": t.name, "employee_id": t.employee_id, "designation": t.designation} for t in teachers]
