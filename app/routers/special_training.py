import logging
import uuid
import json
from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, or_

from app.database.database import get_db
from app.models.department import Department
from app.models.batch import Batch
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.special_training import (
    SpecialTraining,
    SpecialTrainingSubject,
    SpecialTrainingEnrollment,
    SpecialTrainingTimetable,
    SpecialTrainingStaffAssignment,
    SpecialTrainingSession,
    SpecialTrainingMark,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/special-trainings", tags=["Special Training"])

def _resolve_teacher_entity(
    db: Session,
    payload_teacher_id: Optional[str] = None,
    teacher_verification_token: Optional[str] = None,
    authorization: Optional[str] = None
) -> Optional[Teacher]:
    raw = None
    if payload_teacher_id and payload_teacher_id.strip():
        raw = payload_teacher_id.strip()
    elif teacher_verification_token and "veri-token-" in teacher_verification_token:
        raw = teacher_verification_token.split("veri-token-")[-1].strip()
    elif authorization and "Bearer " in authorization:
        raw_auth = authorization.replace("Bearer ", "").strip()
        if "mock-jwt-teacher-" in raw_auth:
            raw = raw_auth.split("mock-jwt-teacher-")[-1].strip()
        else:
            raw = raw_auth

    if not raw:
        return None

    teacher = db.query(Teacher).filter(
        or_(
            Teacher.id == raw,
            Teacher.employee_id == raw,
            func.lower(Teacher.email) == raw.lower()
        )
    ).first()
    return teacher

def _resolve_request_teacher_id(
    db: Session,
    payload_teacher_id: Optional[str] = None,
    teacher_verification_token: Optional[str] = None,
    authorization: Optional[str] = None
) -> Optional[str]:
    teacher = _resolve_teacher_entity(db, payload_teacher_id, teacher_verification_token, authorization)
    if teacher:
        return teacher.id
    if payload_teacher_id and payload_teacher_id.strip():
        return payload_teacher_id.strip()
    return None


# ============================================================================
# Pydantic Schemas
# ============================================================================

class SpecialTrainingBase(BaseModel):
    name: str
    batch_name: str
    batch_id: Optional[str] = None
    trainer_name: Optional[str] = None
    trainer_organization: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    venue: Optional[str] = None

class SpecialTrainingCreate(SpecialTrainingBase):
    pass

class SpecialTrainingUpdate(SpecialTrainingBase):
    pass

class SpecialTrainingResponse(SpecialTrainingBase):
    id: str
    created_at: datetime
    updated_at: datetime
    enrolled_count: int = 0
    departments_count: int = 0
    timetable_slots_count: int = 0
    subjects_count: int = 0

    class Config:
        from_attributes = True

class TrainingSubjectBase(BaseModel):
    name: str
    code: Optional[str] = None
    trainer_name: Optional[str] = None
    venue: Optional[str] = None
    description: Optional[str] = None

class TrainingSubjectCreate(TrainingSubjectBase):
    pass

class TrainingSubjectUpdate(TrainingSubjectBase):
    pass

class TrainingSubjectResponse(TrainingSubjectBase):
    id: str
    training_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class EnrollStudentsRequest(BaseModel):
    student_ids: List[str]

class TimetableSlotCreate(BaseModel):
    day_of_week: str
    period_id: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    topic: Optional[str] = None
    trainer_name: Optional[str] = None
    venue: Optional[str] = None
    teacher_ids: List[str] = []

class StartSessionRequest(BaseModel):
    training_id: str
    date: date
    period_id: str

class MarkStudentRequest(BaseModel):
    student_id: Optional[str] = None
    roll_no: Optional[str] = None
    status: str = "PRESENT" # PRESENT or ABSENT
    method: str = "BARCODE_SCAN" # BARCODE_SCAN or MANUAL_ENTRY
    teacher_id: Optional[str] = None

class SubmitSessionRequest(BaseModel):
    marked_student_ids: List[str] = []
    teacher_id: Optional[str] = None

class TimelineStructurePayload(BaseModel):
    timeline: List[dict]
    include_saturday: Optional[bool] = False



# ============================================================================
# 1. Special Trainings Management (CRUD)
# ============================================================================

@router.get("", response_model=List[SpecialTrainingResponse])
def get_all_special_trainings(db: Session = Depends(get_db)):
    trainings = db.query(SpecialTraining).order_by(SpecialTraining.created_at.desc()).all()
    results = []
    for t in trainings:
        enrolled_count = db.query(SpecialTrainingEnrollment).filter(
            SpecialTrainingEnrollment.training_id == t.id
        ).count()
        
        # Count distinct departments of enrolled students
        dept_count = db.query(func.count(distinct(Student.department_id))).join(
            SpecialTrainingEnrollment, SpecialTrainingEnrollment.student_id == Student.id
        ).filter(SpecialTrainingEnrollment.training_id == t.id).scalar() or 0

        slots_count = db.query(SpecialTrainingTimetable).filter(
            SpecialTrainingTimetable.training_id == t.id
        ).count()

        subjects_count = db.query(SpecialTrainingSubject).filter(
            SpecialTrainingSubject.training_id == t.id
        ).count()

        results.append(SpecialTrainingResponse(
            id=t.id,
            name=t.name,
            batch_id=t.batch_id,
            batch_name=t.batch_name,
            trainer_name=t.trainer_name,
            trainer_organization=t.trainer_organization,
            description=t.description,
            start_date=t.start_date,
            end_date=t.end_date,
            venue=t.venue,
            created_at=t.created_at,
            updated_at=t.updated_at,
            enrolled_count=enrolled_count,
            departments_count=dept_count,
            timetable_slots_count=slots_count,
            subjects_count=subjects_count
        ))
    return results

@router.post("", response_model=SpecialTrainingResponse)
def create_special_training(payload: SpecialTrainingCreate, db: Session = Depends(get_db)):
    # If batch_id not provided, resolve from batch_name if available
    batch_id = payload.batch_id
    if not batch_id and payload.batch_name:
        b = db.query(Batch).filter(Batch.batch_name == payload.batch_name).first()
        if b:
            batch_id = b.id

    training = SpecialTraining(
        name=payload.name,
        batch_id=batch_id,
        batch_name=payload.batch_name,
        trainer_name=payload.trainer_name,
        trainer_organization=payload.trainer_organization,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        venue=payload.venue
    )
    db.add(training)
    db.commit()
    db.refresh(training)

    return SpecialTrainingResponse(
        id=training.id,
        name=training.name,
        batch_id=training.batch_id,
        batch_name=training.batch_name,
        trainer_name=training.trainer_name,
        trainer_organization=training.trainer_organization,
        description=training.description,
        start_date=training.start_date,
        end_date=training.end_date,
        venue=training.venue,
        created_at=training.created_at,
        updated_at=training.updated_at,
        enrolled_count=0,
        departments_count=0,
        timetable_slots_count=0,
        subjects_count=0
    )

@router.get("/{training_id}")
def get_special_training(training_id: str, db: Session = Depends(get_db)):
    t = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Special training not found.")

    enrolled_count = db.query(SpecialTrainingEnrollment).filter(
        SpecialTrainingEnrollment.training_id == t.id
    ).count()

    dept_count = db.query(func.count(distinct(Student.department_id))).join(
        SpecialTrainingEnrollment, SpecialTrainingEnrollment.student_id == Student.id
    ).filter(SpecialTrainingEnrollment.training_id == t.id).scalar() or 0

    slots_count = db.query(SpecialTrainingTimetable).filter(
        SpecialTrainingTimetable.training_id == t.id
    ).count()

    subjects_count = db.query(SpecialTrainingSubject).filter(
        SpecialTrainingSubject.training_id == t.id
    ).count()

    return {
        "id": t.id,
        "name": t.name,
        "batch_id": t.batch_id,
        "batch_name": t.batch_name,
        "trainer_name": t.trainer_name,
        "trainer_organization": t.trainer_organization,
        "description": t.description,
        "start_date": t.start_date,
        "end_date": t.end_date,
        "venue": t.venue,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "enrolled_count": enrolled_count,
        "departments_count": dept_count,
        "timetable_slots_count": slots_count,
        "subjects_count": subjects_count
    }

@router.put("/{training_id}")
def update_special_training(training_id: str, payload: SpecialTrainingUpdate, db: Session = Depends(get_db)):
    t = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Special training not found.")

    t.name = payload.name
    t.batch_name = payload.batch_name
    t.batch_id = payload.batch_id or t.batch_id
    t.trainer_name = payload.trainer_name
    t.trainer_organization = payload.trainer_organization
    t.description = payload.description
    t.start_date = payload.start_date
    t.end_date = payload.end_date
    t.venue = payload.venue

    db.commit()
    db.refresh(t)
    return {"message": "Special training updated successfully."}

@router.delete("/{training_id}")
def delete_special_training(training_id: str, db: Session = Depends(get_db)):
    t = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Special training not found.")

    try:
        # Cascade will handle child tables via DB cascade & ORM
        db.delete(t)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Failed to delete special training %s: %s", training_id, e)
        raise HTTPException(status_code=400, detail=f"Cannot delete special training: {str(e)}")

    return {"message": "Special training deleted successfully."}


# ============================================================================
# 1.5 Special Training Subjects Management (CRUD)
# ============================================================================

@router.get("/{training_id}/subjects", response_model=List[TrainingSubjectResponse])
def get_training_subjects(training_id: str, db: Session = Depends(get_db)):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")

    subjects = db.query(SpecialTrainingSubject).filter(
        SpecialTrainingSubject.training_id == training_id
    ).order_by(SpecialTrainingSubject.created_at.asc()).all()

    return subjects

@router.post("/{training_id}/subjects", response_model=TrainingSubjectResponse, status_code=status.HTTP_201_CREATED)
def create_training_subject(
    training_id: str,
    payload: TrainingSubjectCreate,
    db: Session = Depends(get_db)
):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")

    cleaned_name = payload.name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Subject name is required.")

    subject = SpecialTrainingSubject(
        training_id=training_id,
        name=cleaned_name,
        code=payload.code.strip() if payload.code else None,
        trainer_name=payload.trainer_name.strip() if payload.trainer_name else (training.trainer_name or None),
        venue=payload.venue.strip() if payload.venue else (training.venue or None),
        description=payload.description.strip() if payload.description else None
    )
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject

@router.put("/{training_id}/subjects/{subject_id}", response_model=TrainingSubjectResponse)
def update_training_subject(
    training_id: str,
    subject_id: str,
    payload: TrainingSubjectUpdate,
    db: Session = Depends(get_db)
):
    subject = db.query(SpecialTrainingSubject).filter(
        SpecialTrainingSubject.id == subject_id,
        SpecialTrainingSubject.training_id == training_id
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found for this training.")

    cleaned_name = payload.name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Subject name cannot be empty.")

    subject.name = cleaned_name
    subject.code = payload.code.strip() if payload.code else None
    subject.trainer_name = payload.trainer_name.strip() if payload.trainer_name else None
    subject.venue = payload.venue.strip() if payload.venue else None
    subject.description = payload.description.strip() if payload.description else None

    db.commit()
    db.refresh(subject)
    return subject

@router.delete("/{training_id}/subjects/{subject_id}")
def delete_training_subject(
    training_id: str,
    subject_id: str,
    db: Session = Depends(get_db)
):
    subject = db.query(SpecialTrainingSubject).filter(
        SpecialTrainingSubject.id == subject_id,
        SpecialTrainingSubject.training_id == training_id
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found for this training.")

    db.delete(subject)
    db.commit()
    return {"message": "Subject deleted successfully.", "id": subject_id}


# ============================================================================
# 2. Multi-Department Student Enrollment
# ============================================================================

@router.get("/{training_id}/students")
def get_training_students(
    training_id: str,
    department_id: Optional[str] = None,
    section: Optional[str] = None,
    search: Optional[str] = None,
    all_batches: bool = False,
    db: Session = Depends(get_db)
):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")


    # 1. Enrolled students
    enrolled_query = db.query(
        Student.id,
        Student.roll_no,
        Student.name,
        Student.department_id,
        Department.name.label("department_name"),
        Student.section,
        Student.semester,
        SpecialTrainingEnrollment.enrolled_at
    ).join(
        SpecialTrainingEnrollment, SpecialTrainingEnrollment.student_id == Student.id
    ).outerjoin(
        Department, Department.id == Student.department_id
    ).filter(
        SpecialTrainingEnrollment.training_id == training_id
    )

    if department_id:
        enrolled_query = enrolled_query.filter(Student.department_id == department_id)
    if section:
        enrolled_query = enrolled_query.filter(Student.section == section)
    if search:
        s_term = f"%{search}%"
        enrolled_query = enrolled_query.filter(
            or_(Student.name.ilike(s_term), Student.roll_no.ilike(s_term))
        )

    enrolled = [
        {
            "id": r.id,
            "roll_no": r.roll_no,
            "name": r.name,
            "department_id": r.department_id,
            "department_name": r.department_name or "N/A",
            "section": r.section or "N/A",
            "semester": r.semester,
            "enrolled_at": r.enrolled_at.isoformat() if r.enrolled_at else None
        }
        for r in enrolled_query.order_by(Student.roll_no).all()
    ]

    enrolled_ids = {e["id"] for e in enrolled}

    # 2. Available students from matching batch across ALL departments
    available_query = db.query(
        Student.id,
        Student.roll_no,
        Student.name,
        Student.department_id,
        Department.name.label("department_name"),
        Student.section,
        Student.semester
    ).outerjoin(
        Department, Department.id == Student.department_id
    ).outerjoin(
        Batch, Batch.id == Student.batch_id
    )

    # Filter to matching batch_name if set
    if training.batch_name and not all_batches:
        available_query = available_query.filter(
            or_(Batch.batch_name == training.batch_name, Student.batch_id == training.batch_id)
        )


    if department_id:
        available_query = available_query.filter(Student.department_id == department_id)
    if section:
        available_query = available_query.filter(Student.section == section)
    if search:
        s_term = f"%{search}%"
        available_query = available_query.filter(
            or_(Student.name.ilike(s_term), Student.roll_no.ilike(s_term))
        )

    all_eligible = available_query.order_by(Student.roll_no).all()
    available = [
        {
            "id": r.id,
            "roll_no": r.roll_no,
            "name": r.name,
            "department_id": r.department_id,
            "department_name": r.department_name or "N/A",
            "section": r.section or "N/A",
            "semester": r.semester
        }
        for r in all_eligible if r.id not in enrolled_ids
    ]

    return {
        "enrolled": enrolled,
        "available": available,
        "enrolled_count": len(enrolled),
        "available_count": len(available)
    }

@router.post("/{training_id}/enroll")
def enroll_students(
    training_id: str,
    payload: EnrollStudentsRequest,
    db: Session = Depends(get_db)
):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")

    if not payload.student_ids:
        return {"enrolled_count": 0, "message": "No students selected."}

    # Fetch existing enrolled
    existing_enrolled = set(
        s[0] for s in db.query(SpecialTrainingEnrollment.student_id).filter(
            SpecialTrainingEnrollment.training_id == training_id,
            SpecialTrainingEnrollment.student_id.in_(payload.student_ids)
        ).all()
    )

    to_add = [sid for sid in payload.student_ids if sid not in existing_enrolled]
    for sid in to_add:
        db.add(SpecialTrainingEnrollment(training_id=training_id, student_id=sid))

    db.commit()
    total_enrolled = db.query(SpecialTrainingEnrollment).filter(
        SpecialTrainingEnrollment.training_id == training_id
    ).count()

    return {
        "enrolled_count": len(to_add),
        "total_enrolled": total_enrolled,
        "message": f"Successfully enrolled {len(to_add)} students into {training.name}."
    }

@router.post("/{training_id}/unenroll")
def unenroll_students(
    training_id: str,
    payload: EnrollStudentsRequest,
    db: Session = Depends(get_db)
):
    if not payload.student_ids:
        return {"removed_count": 0}

    deleted = db.query(SpecialTrainingEnrollment).filter(
        SpecialTrainingEnrollment.training_id == training_id,
        SpecialTrainingEnrollment.student_id.in_(payload.student_ids)
    ).delete(synchronize_session=False)

    db.commit()
    return {"removed_count": deleted, "message": f"Unenrolled {deleted} students."}


# ============================================================================
# 3. Timetable Slots & Multiple Staff Assignment
# ============================================================================

@router.get("/{training_id}/timeline-structure")
def get_training_timeline_structure(training_id: str, db: Session = Depends(get_db)):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")

    if training.timeline_config:
        try:
            return json.loads(training.timeline_config)
        except Exception:
            pass
    return {"timeline": None, "include_saturday": False}

@router.put("/{training_id}/timeline-structure")
def update_training_timeline_structure(
    training_id: str,
    payload: TimelineStructurePayload,
    db: Session = Depends(get_db)
):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")

    training.timeline_config = json.dumps({
        "timeline": payload.timeline,
        "include_saturday": payload.include_saturday
    })

    # Update slot start and end times for any matching period in the new timeline
    for item in payload.timeline:
        if item.get("type") == "period" and item.get("number") is not None:
            period_code = f"P{item.get('number')}"
            start_time = item.get("start")
            end_time = item.get("end")
            if start_time or end_time:
                matching_slots = db.query(SpecialTrainingTimetable).filter(
                    SpecialTrainingTimetable.training_id == training_id,
                    SpecialTrainingTimetable.period_id == period_code
                ).all()
                for slot in matching_slots:
                    if start_time:
                        slot.start_time = start_time
                    if end_time:
                        slot.end_time = end_time

    db.commit()
    return {"message": "Timeline structure updated successfully."}

@router.get("/{training_id}/timetable")
def get_training_timetable(training_id: str, db: Session = Depends(get_db)):
    slots = db.query(SpecialTrainingTimetable).filter(
        SpecialTrainingTimetable.training_id == training_id
    ).order_by(SpecialTrainingTimetable.day_of_week, SpecialTrainingTimetable.period_id).all()

    results = []
    for s in slots:
        staff_rows = db.query(
            Teacher.id,
            Teacher.name,
            Teacher.email,
            Department.name.label("department_name")
        ).join(
            SpecialTrainingStaffAssignment, SpecialTrainingStaffAssignment.teacher_id == Teacher.id
        ).outerjoin(
            Department, Department.id == Teacher.department_id
        ).filter(
            SpecialTrainingStaffAssignment.training_id == training_id,
            SpecialTrainingStaffAssignment.day_of_week == s.day_of_week,
            SpecialTrainingStaffAssignment.period_id == s.period_id
        ).all()

        results.append({
            "id": s.id,
            "training_id": s.training_id,
            "day_of_week": s.day_of_week,
            "period_id": s.period_id,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "topic": s.topic,
            "trainer_name": s.trainer_name,
            "venue": s.venue,
            "assigned_staff": [
                {
                    "id": staff.id,
                    "name": staff.name,
                    "email": staff.email,
                    "department_name": staff.department_name or "N/A"
                }
                for staff in staff_rows
            ]
        })
    return results

@router.post("/{training_id}/timetable")
def create_or_update_timetable_slot(
    training_id: str,
    payload: TimetableSlotCreate,
    db: Session = Depends(get_db)
):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")

    # 1. Slot
    slot = db.query(SpecialTrainingTimetable).filter(
        SpecialTrainingTimetable.training_id == training_id,
        SpecialTrainingTimetable.day_of_week == payload.day_of_week.upper(),
        SpecialTrainingTimetable.period_id == payload.period_id.upper()
    ).first()

    if not slot:
        slot = SpecialTrainingTimetable(
            training_id=training_id,
            day_of_week=payload.day_of_week.upper(),
            period_id=payload.period_id.upper(),
            start_time=payload.start_time,
            end_time=payload.end_time,
            topic=payload.topic,
            trainer_name=payload.trainer_name or training.trainer_name,
            venue=payload.venue or training.venue
        )
        db.add(slot)
    else:
        slot.start_time = payload.start_time
        slot.end_time = payload.end_time
        slot.topic = payload.topic
        slot.trainer_name = payload.trainer_name or training.trainer_name
        slot.venue = payload.venue or training.venue

    # 2. Staff Assignments (replace or sync teachers for this slot)
    db.query(SpecialTrainingStaffAssignment).filter(
        SpecialTrainingStaffAssignment.training_id == training_id,
        SpecialTrainingStaffAssignment.day_of_week == payload.day_of_week.upper(),
        SpecialTrainingStaffAssignment.period_id == payload.period_id.upper()
    ).delete(synchronize_session=False)

    for tid in payload.teacher_ids:
        db.add(SpecialTrainingStaffAssignment(
            training_id=training_id,
            day_of_week=payload.day_of_week.upper(),
            period_id=payload.period_id.upper(),
            teacher_id=tid
        ))

    db.commit()
    db.refresh(slot)
    return {"message": "Timetable slot and staff assignments saved successfully.", "slot_id": slot.id}

@router.delete("/{training_id}/timetable/{slot_id}")
def delete_timetable_slot(training_id: str, slot_id: str, db: Session = Depends(get_db)):
    slot = db.query(SpecialTrainingTimetable).filter(
        SpecialTrainingTimetable.id == slot_id,
        SpecialTrainingTimetable.training_id == training_id
    ).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Timetable slot not found.")

    # Remove staff assignments for this slot
    db.query(SpecialTrainingStaffAssignment).filter(
        SpecialTrainingStaffAssignment.training_id == training_id,
        SpecialTrainingStaffAssignment.day_of_week == slot.day_of_week,
        SpecialTrainingStaffAssignment.period_id == slot.period_id
    ).delete(synchronize_session=False)

    db.delete(slot)
    db.commit()
    return {"message": "Timetable slot deleted successfully."}


# ============================================================================
# 4. Teacher Portal Integration & Concurrent Attendance Taking
# ============================================================================

@router.get("/teacher/today")
def get_teacher_today_trainings(
    teacher_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    today = datetime.now()
    today_date = today.date()
    day_mapping = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}
    dow = day_mapping[today.weekday()]

    # If teacher_id not provided, list all training slots for today
    query = db.query(
        SpecialTrainingTimetable,
        SpecialTraining
    ).join(
        SpecialTraining, SpecialTraining.id == SpecialTrainingTimetable.training_id
    ).filter(
        SpecialTrainingTimetable.day_of_week == dow
    )

    if teacher_id:
        query = query.join(
            SpecialTrainingStaffAssignment,
            (SpecialTrainingStaffAssignment.training_id == SpecialTrainingTimetable.training_id) &
            (SpecialTrainingStaffAssignment.day_of_week == SpecialTrainingTimetable.day_of_week) &
            (SpecialTrainingStaffAssignment.period_id == SpecialTrainingTimetable.period_id)
        ).filter(
            SpecialTrainingStaffAssignment.teacher_id == teacher_id
        )

    slots = query.all()
    results = []

    for slot, training in slots:
        # Check if session exists for today (case-insensitive period matching)
        clean_slot_period = slot.period_id.strip().upper().replace("TR-", "")
        sess = db.query(SpecialTrainingSession).filter(
            SpecialTrainingSession.training_id == training.id,
            SpecialTrainingSession.date == today_date,
            (func.upper(SpecialTrainingSession.period_id) == clean_slot_period) |
            (func.upper(SpecialTrainingSession.period_id) == slot.period_id.strip().upper())
        ).first()

        enrolled_count = db.query(SpecialTrainingEnrollment).filter(
            SpecialTrainingEnrollment.training_id == training.id
        ).count()

        present_count = 0
        marked_count = 0
        if sess:
            present_count = db.query(SpecialTrainingMark).filter(
                SpecialTrainingMark.session_id == sess.id,
                SpecialTrainingMark.status == "PRESENT"
            ).count()
            marked_count = db.query(SpecialTrainingMark).filter(
                SpecialTrainingMark.session_id == sess.id
            ).count()

        # Assigned staff names
        staff_names = [
            r[0] for r in db.query(Teacher.name).join(
                SpecialTrainingStaffAssignment, SpecialTrainingStaffAssignment.teacher_id == Teacher.id
            ).filter(
                SpecialTrainingStaffAssignment.training_id == training.id,
                SpecialTrainingStaffAssignment.day_of_week == slot.day_of_week,
                SpecialTrainingStaffAssignment.period_id == slot.period_id
            ).all()
        ]

        results.append({
            "slot_id": slot.id,
            "training_id": training.id,
            "training_name": training.name,
            "batch_name": training.batch_name,
            "period_id": slot.period_id,
            "day_of_week": slot.day_of_week,
            "start_time": slot.start_time,
            "end_time": slot.end_time,
            "topic": slot.topic,
            "trainer_name": slot.trainer_name or training.trainer_name,
            "venue": slot.venue or training.venue,
            "session_id": sess.id if sess else None,
            "session_status": sess.status if sess else "SCHEDULED",
            "enrolled_count": enrolled_count,
            "present_count": present_count,
            "marked_count": marked_count,
            "assigned_staff": staff_names,
            "date": today_date.isoformat()
        })

    return results

@router.post("/sessions/start-or-get")
def start_or_get_training_session(
    payload: StartSessionRequest,
    db: Session = Depends(get_db)
):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == payload.training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")

    clean_period = payload.period_id.strip().upper().replace("TR-", "")
    session = db.query(SpecialTrainingSession).filter(
        SpecialTrainingSession.training_id == payload.training_id,
        SpecialTrainingSession.date == payload.date,
        (func.upper(SpecialTrainingSession.period_id) == clean_period) |
        (func.upper(SpecialTrainingSession.period_id) == payload.period_id.strip().upper())
    ).first()

    if not session:
        session = SpecialTrainingSession(
            training_id=payload.training_id,
            date=payload.date,
            period_id=clean_period,
            status="ACTIVE",
            created_at=datetime.now()
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    # Return session with full enrolled roster and existing marks
    return get_training_session_details(session.id, db)

@router.get("/sessions/{session_id}")
def get_training_session_details(session_id: str, db: Session = Depends(get_db)):
    session = db.query(SpecialTrainingSession).filter(SpecialTrainingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Training session not found.")

    training = session.training

    # All enrolled students
    enrolled_students = db.query(
        Student.id,
        Student.roll_no,
        Student.name,
        Student.department_id,
        Department.name.label("department_name"),
        Student.section
    ).join(
        SpecialTrainingEnrollment, SpecialTrainingEnrollment.student_id == Student.id
    ).outerjoin(
        Department, Department.id == Student.department_id
    ).filter(
        SpecialTrainingEnrollment.training_id == session.training_id
    ).order_by(Student.roll_no).all()

    # All marks for this session
    marks = db.query(SpecialTrainingMark).filter(
        SpecialTrainingMark.session_id == session_id
    ).all()
    marks_by_student_id = {m.student_id: m for m in marks}

    roster = []
    present_count = 0
    absent_count = 0

    for s in enrolled_students:
        mark = marks_by_student_id.get(s.id)
        status = mark.status if mark else "NOT_MARKED"
        if status == "PRESENT":
            present_count += 1
        elif status == "ABSENT":
            absent_count += 1

        teacher_name = None
        if mark and mark.marked_by:
            teacher_name = mark.marked_by.name
        elif mark and mark.marked_by_teacher_id:
            t = db.query(Teacher).filter(Teacher.id == mark.marked_by_teacher_id).first()
            if t:
                teacher_name = t.name

        roster.append({
            "student_id": s.id,
            "roll_no": s.roll_no,
            "name": s.name,
            "department_id": s.department_id,
            "department_name": s.department_name or "N/A",
            "section": s.section or "N/A",
            "status": status,
            "method": mark.method if mark else None,
            "marked_by": teacher_name,
            "marked_at": mark.marked_at.isoformat() if (mark and mark.marked_at) else None
        })

    # List of all faculty who marked students present in this session
    contributing_teacher_ids = {m.marked_by_teacher_id for m in marks if m.marked_by_teacher_id and m.status == "PRESENT"}
    contributing_teachers = [
        t[0] for t in db.query(Teacher.name).filter(Teacher.id.in_(contributing_teacher_ids)).all()
    ] if contributing_teacher_ids else []

    return {
        "session_id": session.id,
        "training_id": training.id,
        "training_name": training.name,
        "date": session.date.isoformat(),
        "period_id": session.period_id,
        "status": session.status,
        "total_enrolled": len(enrolled_students),
        "present_count": present_count,
        "absent_count": absent_count,
        "roster": roster,
        "contributing_teachers": contributing_teachers
    }

@router.post("/sessions/{session_id}/mark")
def mark_student_attendance(
    session_id: str,
    payload: MarkStudentRequest,
    teacher_verification_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    session = db.query(SpecialTrainingSession).filter(SpecialTrainingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Training session not found.")

    teacher = _resolve_teacher_entity(
        db,
        payload.teacher_id,
        teacher_verification_token,
        authorization
    )
    resolved_teacher_id = teacher.id if teacher else None

    # Find student by student_id or roll_no (case-insensitive)
    student = None
    if payload.student_id:
        student = db.query(Student).filter(Student.id == payload.student_id).first()
    elif payload.roll_no:
        student = db.query(Student).filter(func.lower(Student.roll_no) == payload.roll_no.strip().lower()).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    # Check student is enrolled in this training
    is_enrolled = db.query(SpecialTrainingEnrollment).filter(
        SpecialTrainingEnrollment.training_id == session.training_id,
        SpecialTrainingEnrollment.student_id == student.id
    ).first()
    if not is_enrolled:
        raise HTTPException(
            status_code=400,
            detail=f"Student {student.name} ({student.roll_no}) is not enrolled in this special training."
        )

    # Upsert mark
    mark = db.query(SpecialTrainingMark).filter(
        SpecialTrainingMark.session_id == session_id,
        SpecialTrainingMark.student_id == student.id
    ).first()

    target_status = payload.status.upper()
    marking_teacher = resolved_teacher_id if target_status == "PRESENT" else None

    if not mark:
        mark = SpecialTrainingMark(
            session_id=session_id,
            student_id=student.id,
            status=target_status,
            marked_by_teacher_id=marking_teacher,
            method=payload.method,
            marked_at=datetime.now()
        )
        db.add(mark)
    else:
        mark.status = target_status
        if target_status == "PRESENT":
            mark.marked_by_teacher_id = resolved_teacher_id or mark.marked_by_teacher_id
        else:
            mark.marked_by_teacher_id = None
        mark.method = payload.method
        mark.marked_at = datetime.now()

    db.commit()
    db.refresh(mark)

    # Return refreshed counts
    present_count = db.query(SpecialTrainingMark).filter(
        SpecialTrainingMark.session_id == session_id,
        SpecialTrainingMark.status == "PRESENT"
    ).count()

    teacher_obj = mark.marked_by or (teacher if mark.marked_by_teacher_id == (teacher.id if teacher else None) else None)
    if not teacher_obj and mark.marked_by_teacher_id:
        teacher_obj = db.query(Teacher).filter(Teacher.id == mark.marked_by_teacher_id).first()

    return {
        "success": True,
        "student_id": student.id,
        "roll_no": student.roll_no,
        "name": student.name,
        "status": mark.status,
        "present_count": present_count,
        "marked_by": teacher_obj.name if teacher_obj else None,
        "message": f"{student.name} marked {mark.status}."
    }

@router.post("/sessions/{session_id}/submit")
def submit_training_session(
    session_id: str,
    payload: SubmitSessionRequest,
    teacher_verification_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    session = db.query(SpecialTrainingSession).filter(SpecialTrainingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Training session not found.")

    resolved_teacher_id = _resolve_request_teacher_id(
        db,
        payload.teacher_id,
        teacher_verification_token,
        authorization
    )

    all_enrolled_ids = [
        s[0] for s in db.query(SpecialTrainingEnrollment.student_id).filter(
            SpecialTrainingEnrollment.training_id == session.training_id
        ).all()
    ]

    # Combine all students already marked PRESENT by ANY teacher with newly submitted student IDs
    existing_presents = {
        m.student_id for m in db.query(SpecialTrainingMark).filter(
            SpecialTrainingMark.session_id == session_id,
            SpecialTrainingMark.status == "PRESENT"
        ).all()
    }
    submitted_set = set(payload.marked_student_ids) if payload.marked_student_ids else set()
    final_present_ids = existing_presents.union(submitted_set)

    for sid in all_enrolled_ids:
        mark = db.query(SpecialTrainingMark).filter(
            SpecialTrainingMark.session_id == session_id,
            SpecialTrainingMark.student_id == sid
        ).first()

        is_present = sid in final_present_ids
        target_status = "PRESENT" if is_present else "ABSENT"

        if not mark:
            db.add(SpecialTrainingMark(
                session_id=session_id,
                student_id=sid,
                status=target_status,
                marked_by_teacher_id=resolved_teacher_id if is_present else None,
                method="MANUAL_ENTRY",
                marked_at=datetime.now()
            ))
        else:
            mark.status = target_status
            if is_present:
                if not mark.marked_by_teacher_id and resolved_teacher_id:
                    mark.marked_by_teacher_id = resolved_teacher_id
            else:
                mark.marked_by_teacher_id = None

    session.status = "COMPLETED"
    session.completed_at = datetime.now()
    db.commit()

    total_present = db.query(SpecialTrainingMark).filter(
        SpecialTrainingMark.session_id == session_id,
        SpecialTrainingMark.status == "PRESENT"
    ).count()

    return {
        "success": True,
        "message": f"Special training attendance finalized successfully. {total_present} of {len(all_enrolled_ids)} students marked present.",
        "present_count": total_present,
        "total_enrolled": len(all_enrolled_ids)
    }


# ============================================================================
# 5. Special Training Reports
# ============================================================================

@router.get("/{training_id}/reports/daily")
def get_daily_training_report(
    training_id: str,
    date: Optional[date] = None,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")

    target_date = date or datetime.now().date()

    # Find sessions for that date
    sessions = db.query(SpecialTrainingSession).filter(
        SpecialTrainingSession.training_id == training_id,
        SpecialTrainingSession.date == target_date
    ).all()
    session_ids = [s.id for s in sessions]

    # Enrolled students
    query = db.query(
        Student.id,
        Student.roll_no,
        Student.name,
        Student.department_id,
        Department.name.label("department_name"),
        Student.section
    ).join(
        SpecialTrainingEnrollment, SpecialTrainingEnrollment.student_id == Student.id
    ).outerjoin(
        Department, Department.id == Student.department_id
    ).filter(
        SpecialTrainingEnrollment.training_id == training_id
    )

    if department_id:
        query = query.filter(Student.department_id == department_id)

    students = query.order_by(Student.roll_no).all()

    # Fetch marks for these sessions
    marks = {}
    if session_ids:
        raw_marks = db.query(SpecialTrainingMark).filter(
            SpecialTrainingMark.session_id.in_(session_ids)
        ).all()
        for m in raw_marks:
            # If present in any period today, mark present
            if m.student_id not in marks or m.status == "PRESENT":
                marks[m.student_id] = m

    records = []
    present_count = 0
    absent_count = 0

    for s in students:
        mark = marks.get(s.id)
        # If no session or no mark recorded yet, status is ABSENT if session completed or ABSENT by default
        status = mark.status if mark else "ABSENT"
        if status == "PRESENT":
            present_count += 1
        else:
            absent_count += 1

        teacher_name = mark.marked_by.name if (mark and mark.marked_by) else None
        marked_at = mark.marked_at.isoformat() if mark else None

        records.append({
            "student_id": s.id,
            "roll_no": s.roll_no,
            "name": s.name,
            "department_id": s.department_id,
            "department_name": s.department_name or "N/A",
            "section": s.section or "N/A",
            "status": status,
            "marked_by": teacher_name,
            "marked_at": marked_at,
            "method": mark.method if mark else None
        })

    total = len(students)
    rate = round((present_count / total * 100), 1) if total > 0 else 0.0

    return {
        "training_id": training.id,
        "training_name": training.name,
        "trainer_name": training.trainer_name,
        "date": target_date.isoformat(),
        "total_enrolled": total,
        "present_count": present_count,
        "absent_count": absent_count,
        "attendance_rate": rate,
        "records": records
    }

@router.get("/{training_id}/reports/student-wise")
def get_student_wise_training_report(
    training_id: str,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")

    # Total distinct sessions conducted
    total_sessions = db.query(SpecialTrainingSession).filter(
        SpecialTrainingSession.training_id == training_id
    ).count()

    query = db.query(
        Student.id,
        Student.roll_no,
        Student.name,
        Student.department_id,
        Department.name.label("department_name"),
        Student.section
    ).join(
        SpecialTrainingEnrollment, SpecialTrainingEnrollment.student_id == Student.id
    ).outerjoin(
        Department, Department.id == Student.department_id
    ).filter(
        SpecialTrainingEnrollment.training_id == training_id
    )

    if department_id:
        query = query.filter(Student.department_id == department_id)

    students = query.order_by(Student.roll_no).all()

    # Pre-fetch attendance counts for all students in this training
    attended_counts = dict(
        db.query(
            SpecialTrainingMark.student_id,
            func.count(SpecialTrainingMark.id)
        ).join(
            SpecialTrainingSession, SpecialTrainingSession.id == SpecialTrainingMark.session_id
        ).filter(
            SpecialTrainingSession.training_id == training_id,
            SpecialTrainingMark.status == "PRESENT"
        ).group_by(SpecialTrainingMark.student_id).all()
    )

    records = []
    for s in students:
        attended = attended_counts.get(s.id, 0)
        percentage = round((attended / total_sessions * 100), 1) if total_sessions > 0 else 100.0

        category = "Good"
        if percentage < 65.0:
            category = "Critical"
        elif percentage < 75.0:
            category = "Average"

        records.append({
            "student_id": s.id,
            "roll_no": s.roll_no,
            "name": s.name,
            "department_id": s.department_id,
            "department_name": s.department_name or "N/A",
            "section": s.section or "N/A",
            "attended_sessions": attended,
            "total_sessions": total_sessions,
            "percentage": percentage,
            "category": category
        })

    return {
        "training_id": training.id,
        "training_name": training.name,
        "total_sessions": total_sessions,
        "students": records
    }

@router.get("/{training_id}/reports/absentees")
def get_absentees_analysis(
    training_id: str,
    min_absent_days: Optional[int] = Query(None, description="Filter for missing >= X days/sessions, e.g. 1, 5, 10"),
    max_percentage: Optional[float] = Query(None, description="Filter for attendance <= Y%"),
    department_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    training = db.query(SpecialTraining).filter(SpecialTraining.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Special training not found.")

    total_sessions = db.query(SpecialTrainingSession).filter(
        SpecialTrainingSession.training_id == training_id
    ).count()

    query = db.query(
        Student.id,
        Student.roll_no,
        Student.name,
        Student.department_id,
        Department.name.label("department_name"),
        Student.section
    ).join(
        SpecialTrainingEnrollment, SpecialTrainingEnrollment.student_id == Student.id
    ).outerjoin(
        Department, Department.id == Student.department_id
    ).filter(
        SpecialTrainingEnrollment.training_id == training_id
    )

    if department_id:
        query = query.filter(Student.department_id == department_id)

    students = query.order_by(Student.roll_no).all()

    attended_counts = dict(
        db.query(
            SpecialTrainingMark.student_id,
            func.count(SpecialTrainingMark.id)
        ).join(
            SpecialTrainingSession, SpecialTrainingSession.id == SpecialTrainingMark.session_id
        ).filter(
            SpecialTrainingSession.training_id == training_id,
            SpecialTrainingMark.status == "PRESENT"
        ).group_by(SpecialTrainingMark.student_id).all()
    )

    # Get last attended date per student
    last_attended = dict(
        db.query(
            SpecialTrainingMark.student_id,
            func.max(SpecialTrainingSession.date)
        ).join(
            SpecialTrainingSession, SpecialTrainingSession.id == SpecialTrainingMark.session_id
        ).filter(
            SpecialTrainingSession.training_id == training_id,
            SpecialTrainingMark.status == "PRESENT"
        ).group_by(SpecialTrainingMark.student_id).all()
    )

    absentees = []
    min_absent = min_absent_days or 1

    for s in students:
        attended = attended_counts.get(s.id, 0)
        absent_days = max(0, total_sessions - attended)
        percentage = round((attended / total_sessions * 100), 1) if total_sessions > 0 else 0.0

        # Filter criteria:
        # 1. Missing >= min_absent_days (default 1)
        # 2. If max_percentage is specified, must also satisfy percentage <= max_percentage
        if absent_days < min_absent:
            continue
        if max_percentage is not None and percentage > max_percentage:
            continue

        risk_level = "High" if (percentage < 60 or absent_days >= 5) else ("Moderate" if percentage < 75 else "Low")

        absentees.append({
            "student_id": s.id,
            "roll_no": s.roll_no,
            "name": s.name,
            "department_id": s.department_id,
            "department_name": s.department_name or "N/A",
            "section": s.section or "N/A",
            "attended_sessions": attended,
            "absent_days": absent_days,
            "total_sessions": total_sessions,
            "percentage": percentage,
            "risk_level": risk_level,
            "last_attended": last_attended.get(s.id).isoformat() if last_attended.get(s.id) else "Never"
        })

    # Sort by absent_days descending (worst absentees first)
    absentees.sort(key=lambda x: x["absent_days"], reverse=True)

    return {
        "training_id": training.id,
        "training_name": training.name,
        "total_sessions": total_sessions,
        "min_absent_days_filter": min_absent,
        "max_percentage_filter": max_percentage,
        "total_absentees_matched": len(absentees),
        "absentees": absentees
    }
