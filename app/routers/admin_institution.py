from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging
from ..database.database import get_db
from ..models.department import Department
from ..models.batch import Batch
from ..models.student import Student, StudentEnrollment
from ..models.teacher import Teacher
from ..models.subject import Subject
from ..models.attendance import AttendanceSession, AttendanceMark
from ..models.timetable import TeacherAssignment, TimetableStructure
from ..models.section_assignment import SectionSubjectAssignment
from ..models.calendar_override import CalendarOverride
from ..models.day_wise_attendance import DayWiseAttendance
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/institution", tags=["Admin Institution Setup"])


# --- Schemas ---
class BatchBase(BaseModel):
    batch_name: str
    current_year: int
    current_semester: int
    sections_count: int

class BatchCreate(BatchBase):
    pass

class BatchResponse(BatchBase):
    id: str
    department_id: str
    class Config:
        from_attributes = True

class DepartmentBase(BaseModel):
    name: str
    code: str
    morning_entry_time: str | None = None

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentResponse(DepartmentBase):
    id: str
    class Config:
        from_attributes = True

class DepartmentWithBatchesResponse(DepartmentResponse):
    batches: List[BatchResponse] = []

# --- Endpoints ---

@router.get("/departments")
def get_departments(include_batches: bool = False, db: Session = Depends(get_db)):
    departments = db.query(Department).all()
    if include_batches:
        return [DepartmentWithBatchesResponse.model_validate(d) for d in departments]
    return [DepartmentResponse.model_validate(d) for d in departments]

@router.post("/departments", response_model=DepartmentResponse)
def create_department(dept_in: DepartmentCreate, db: Session = Depends(get_db)):
    existing = db.query(Department).filter((Department.code == dept_in.code) | (Department.name == dept_in.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Department with this code or name already exists.")
    
    db_dept = Department(name=dept_in.name, code=dept_in.code, morning_entry_time=dept_in.morning_entry_time)
    db.add(db_dept)
    db.commit()
    db.refresh(db_dept)
    return db_dept

@router.get("/departments/{department_id}/batches", response_model=List[BatchResponse])
def get_department_batches(department_id: str, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")
    return dept.batches

@router.get("/batches/{batch_id}/sections")
def get_batch_sections(batch_id: str, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found.")
        
    from ..models.student import Student
    from ..models.timetable import TimetableStructure
    
    student_secs = [s[0].upper() for s in db.query(Student.section).filter(Student.batch_id == batch_id, Student.section != None).distinct().all() if s[0]]
    tt_secs = [t[0].upper() for t in db.query(TimetableStructure.section_name).filter(TimetableStructure.batch_id == batch_id).distinct().all() if t[0]]
    
    combined = sorted(list(set(student_secs + tt_secs)))
    
    if combined:
        return [{"id": s, "name": f"Section {s}"} for s in combined]

    sec_count = batch.sections_count
    # Generate sections A, B, C... based on count as fallback
    sections = []
    for i in range(sec_count):
        sec_name = chr(65 + i)
        sections.append({
            "id": sec_name,
            "name": f"Section {sec_name}"
        })
    return sections

@router.post("/departments/{department_id}/batches", response_model=BatchResponse)
def create_batch(department_id: str, batch_in: BatchCreate, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")
    
    existing = db.query(Batch).filter(
        Batch.department_id == department_id, 
        Batch.batch_name == batch_in.batch_name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Batch already exists under this department.")
        
    db_batch = Batch(
        department_id=department_id,
        batch_name=batch_in.batch_name,
        current_year=batch_in.current_year,
        current_semester=batch_in.current_semester,
        sections_count=batch_in.sections_count
    )
    db.add(db_batch)

    from ..models.reference import Section, Semester
    for i in range(1, 11):
        if not db.query(Semester).filter(Semester.id == i).first():
            db.add(Semester(id=i, name=f"Semester {i}"))
            
    for i in range(batch_in.sections_count):
        sec_char = chr(65 + i)
        if not db.query(Section).filter(Section.id == sec_char).first():
            db.add(Section(id=sec_char, name=f"Section {sec_char}"))

    db.commit()
    db.refresh(db_batch)
    return db_batch

@router.put("/departments/{department_id}", response_model=DepartmentResponse)
def update_department(department_id: str, dept_in: DepartmentCreate, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")
    
    # Check if new code/name conflicts with another existing department
    existing = db.query(Department).filter(
        (Department.id != department_id) & 
        ((Department.code == dept_in.code) | (Department.name == dept_in.name))
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Another department with this code or name already exists.")

    dept.name = dept_in.name
    dept.code = dept_in.code
    dept.morning_entry_time = dept_in.morning_entry_time
    db.commit()
    db.refresh(dept)
    return dept

@router.put("/departments/{department_id}/batches/{batch_id}", response_model=BatchResponse)
def update_batch(department_id: str, batch_id: str, batch_in: BatchCreate, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.department_id == department_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found in this department.")
    
    # Check for name collisions in the same department
    existing = db.query(Batch).filter(
        Batch.department_id == department_id,
        Batch.batch_name == batch_in.batch_name,
        Batch.id != batch_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Another batch with this name already exists in this department.")
        
    old_semester = batch.current_semester
    old_sections_count = batch.sections_count
    
    if batch_in.sections_count < old_sections_count:
        from ..models.student import Student
        from sqlalchemy import func
        removed_sections = [chr(65 + i) for i in range(batch_in.sections_count, old_sections_count)]
        invalid_students = db.query(Student).filter(
            Student.batch_id == batch_id, 
            func.upper(Student.section).in_(removed_sections)
        ).count()
        if invalid_students > 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot reduce sections. {invalid_students} student(s) belong to the removed sections ({', '.join(removed_sections)})."
            )

    batch.batch_name = batch_in.batch_name
    batch.current_year = batch_in.current_year
    batch.current_semester = batch_in.current_semester
    batch.sections_count = batch_in.sections_count
    
    from ..models.reference import Section, Semester
    for i in range(1, 11):
        if not db.query(Semester).filter(Semester.id == i).first():
            db.add(Semester(id=i, name=f"Semester {i}"))
            
    for i in range(batch_in.sections_count):
        sec_char = chr(65 + i)
        if not db.query(Section).filter(Section.id == sec_char).first():
            db.add(Section(id=sec_char, name=f"Section {sec_char}"))
    
    if old_semester != batch_in.current_semester:
        from ..models.student import Student
        db.query(Student).filter(Student.batch_id == batch_id).update({
            "semester": batch_in.current_semester
        }, synchronize_session=False)
    
    db.commit()
    db.refresh(batch)
    return batch

@router.delete("/departments/{department_id}")
def delete_department(department_id: str, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")
        
    try:
        batch_ids = [b[0] for b in db.query(Batch.id).filter(Batch.department_id == department_id).all()]

        # 1. Students in this department or its batches
        student_filter = (Student.department_id == department_id)
        if batch_ids:
            student_filter = student_filter | (Student.batch_id.in_(batch_ids))
        student_ids = [s[0] for s in db.query(Student.id).filter(student_filter).all()]
        if student_ids:
            db.query(AttendanceMark).filter(AttendanceMark.student_id.in_(student_ids)).delete(synchronize_session=False)
            db.query(DayWiseAttendance).filter(DayWiseAttendance.student_id.in_(student_ids)).delete(synchronize_session=False)
            db.query(StudentEnrollment).filter(StudentEnrollment.student_id.in_(student_ids)).delete(synchronize_session=False)
            db.query(Student).filter(Student.id.in_(student_ids)).delete(synchronize_session=False)

        # 2. Subjects in this department
        subject_ids = [s[0] for s in db.query(Subject.id).filter(Subject.department_id == department_id).all()]
        if subject_ids:
            db.query(AttendanceSession).filter(AttendanceSession.subject_id.in_(subject_ids)).update(
                {AttendanceSession.subject_id: None}, synchronize_session=False
            )
            db.query(TeacherAssignment).filter(TeacherAssignment.subject_id.in_(subject_ids)).delete(synchronize_session=False)
            db.query(SectionSubjectAssignment).filter(SectionSubjectAssignment.subject_id.in_(subject_ids)).delete(synchronize_session=False)
            db.query(Subject).filter(Subject.id.in_(subject_ids)).delete(synchronize_session=False)

        # 3. Teachers in this department
        teacher_ids = [t[0] for t in db.query(Teacher.id).filter(Teacher.department_id == department_id).all()]
        if teacher_ids:
            session_ids = [s[0] for s in db.query(AttendanceSession.id).filter(AttendanceSession.teacher_id.in_(teacher_ids)).all()]
            if session_ids:
                db.query(AttendanceMark).filter(AttendanceMark.session_id.in_(session_ids)).delete(synchronize_session=False)
                db.query(AttendanceSession).filter(AttendanceSession.id.in_(session_ids)).delete(synchronize_session=False)
            db.query(DayWiseAttendance).filter(DayWiseAttendance.marked_by.in_(teacher_ids)).update(
                {DayWiseAttendance.marked_by: None}, synchronize_session=False
            )
            db.query(TeacherAssignment).filter(TeacherAssignment.teacher_id.in_(teacher_ids)).delete(synchronize_session=False)
            db.query(SectionSubjectAssignment).filter(SectionSubjectAssignment.teacher_id.in_(teacher_ids)).delete(synchronize_session=False)
            db.query(Teacher).filter(Teacher.id.in_(teacher_ids)).delete(synchronize_session=False)

        # 4. Timetable Structures (department or its batches)
        tt_filter = (TimetableStructure.department_id == department_id)
        if batch_ids:
            tt_filter = tt_filter | (TimetableStructure.batch_id.in_(batch_ids))
        db.query(TimetableStructure).filter(tt_filter).delete(synchronize_session=False)

        # 5. Teacher Assignments (department or its batches)
        ta_filter = (TeacherAssignment.department_id == department_id)
        if batch_ids:
            ta_filter = ta_filter | (TeacherAssignment.batch_id.in_(batch_ids))
        db.query(TeacherAssignment).filter(ta_filter).delete(synchronize_session=False)

        # 6. Section Subject Assignments (department or its batches)
        ssa_filter = (SectionSubjectAssignment.department_id == department_id)
        if batch_ids:
            ssa_filter = ssa_filter | (SectionSubjectAssignment.batch_id.in_(batch_ids))
        db.query(SectionSubjectAssignment).filter(ssa_filter).delete(synchronize_session=False)

        # 7. Calendar Overrides (department or its batches)
        cal_filter = (CalendarOverride.department_id == department_id)
        if batch_ids:
            cal_filter = cal_filter | (CalendarOverride.batch_id.in_(batch_ids))
        db.query(CalendarOverride).filter(cal_filter).delete(synchronize_session=False)

        # 8. Attendance Sessions: detach department and batch
        db.query(AttendanceSession).filter(AttendanceSession.department_id == department_id).update(
            {AttendanceSession.department_id: None, AttendanceSession.batch_id: None}, synchronize_session=False
        )
        if batch_ids:
            db.query(AttendanceSession).filter(AttendanceSession.batch_id.in_(batch_ids)).update(
                {AttendanceSession.batch_id: None}, synchronize_session=False
            )

        # 9. Student Enrollments
        enr_filter = (StudentEnrollment.department_id == department_id)
        if batch_ids:
            enr_filter = enr_filter | (StudentEnrollment.batch_id.in_(batch_ids))
        db.query(StudentEnrollment).filter(enr_filter).delete(synchronize_session=False)

        # 10. Batches
        db.query(Batch).filter(Batch.department_id == department_id).delete(synchronize_session=False)

        # 11. Department itself
        db.delete(dept)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Failed to delete department %s: %s", department_id, e)
        raise HTTPException(status_code=400, detail=f"Cannot delete department: {str(e)}")
        
    return {"message": "Department deleted successfully."}

@router.delete("/departments/{department_id}/batches/{batch_id}")
def delete_batch(department_id: str, batch_id: str, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.department_id == department_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found.")
        
    try:
        # 1. Timetable Structures
        db.query(TimetableStructure).filter(TimetableStructure.batch_id == batch_id).delete(synchronize_session=False)

        # 2. Timetable Entries (Teacher Assignments)
        db.query(TeacherAssignment).filter(TeacherAssignment.batch_id == batch_id).delete(synchronize_session=False)

        # 3. Section Subject Assignments
        db.query(SectionSubjectAssignment).filter(SectionSubjectAssignment.batch_id == batch_id).delete(synchronize_session=False)

        # 4. Calendar Overrides
        db.query(CalendarOverride).filter(CalendarOverride.batch_id == batch_id).delete(synchronize_session=False)

        # 5. Attendance Sessions: detach batch reference
        db.query(AttendanceSession).filter(AttendanceSession.batch_id == batch_id).update(
            {AttendanceSession.batch_id: None}, synchronize_session=False
        )

        # 6. Student Enrollments
        db.query(StudentEnrollment).filter(StudentEnrollment.batch_id == batch_id).delete(synchronize_session=False)

        # 7. Students in this batch
        student_ids = [s[0] for s in db.query(Student.id).filter(Student.batch_id == batch_id).all()]
        if student_ids:
            db.query(AttendanceMark).filter(AttendanceMark.student_id.in_(student_ids)).delete(synchronize_session=False)
            db.query(DayWiseAttendance).filter(DayWiseAttendance.student_id.in_(student_ids)).delete(synchronize_session=False)
            db.query(StudentEnrollment).filter(StudentEnrollment.student_id.in_(student_ids)).delete(synchronize_session=False)
            db.query(Student).filter(Student.id.in_(student_ids)).delete(synchronize_session=False)

        # 8. Delete Batch
        db.delete(batch)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Failed to delete batch %s: %s", batch_id, e)
        raise HTTPException(status_code=400, detail=f"Cannot delete batch: {str(e)}")
        
    return {"message": "Batch deleted successfully."}

