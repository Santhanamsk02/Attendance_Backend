from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database.database import get_db
from ..models.department import Department
from ..models.batch import Batch
from pydantic import BaseModel

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

    from ..models.reference import Section
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
    
    from ..models.reference import Section
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
        
    counts = []
    if getattr(dept, 'students', []): counts.append(f"{len(dept.students)} students")
    if getattr(dept, 'teachers', []): counts.append(f"{len(dept.teachers)} teachers")
    if getattr(dept, 'subjects', []): counts.append(f"{len(dept.subjects)} subjects")
    if getattr(dept, 'batches', []): counts.append(f"{len(dept.batches)} active cohorts")
        
    if counts:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete. Department contains: {', '.join(counts)}."
        )
        
    try:
        db.delete(dept)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Cannot delete department. Database constraints failed.")
        
    return {"message": "Department deleted successfully."}

@router.delete("/departments/{department_id}/batches/{batch_id}")
def delete_batch(department_id: str, batch_id: str, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.department_id == department_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found.")
        
    if getattr(batch, 'students', []):
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete. Batch contains {len(batch.students)} active students."
        )
        
    try:
        db.delete(batch)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Cannot delete batch. Database constraints failed.")
        
    return {"message": "Batch deleted successfully."}
