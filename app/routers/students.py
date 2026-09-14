from typing import Optional
from fastapi import APIRouter, Depends, Query, status, UploadFile, File, Response
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.student import (
    StudentCreate,
    StudentUpdate,
    StudentResponse,
    StudentListResponse,
    StudentStatsResponse,
    BulkImportResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
)
from app.services.student_service import StudentService

router = APIRouter(prefix="/students", tags=["Students"])


@router.get(
    "",
    response_model=StudentListResponse,
    summary="Get paginated list of students",
    description="Retrieve students with optional search across roll number, name, email and dynamic filters.",
)
def get_students(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search term for roll_no, name, or email"),
    department_id: Optional[str] = Query(None, description="Filter by department ID"),
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    section: Optional[str] = Query(None, description="Filter by section"),
    status: Optional[str] = Query(None, description="Filter by status ('active' | 'inactive')"),
    db: Session = Depends(get_db),
):
    return StudentService.get_students(
        db=db,
        page=page,
        limit=limit,
        search=search,
        department_id=department_id,
        batch_id=batch_id,
        section=section,
        status_filter=status,
    )


@router.get(
    "/stats",
    response_model=StudentStatsResponse,
    summary="Get student statistics",
    description="Retrieve summary statistics for the Admin Dashboard (total, active, departments, recent).",
)
def get_student_stats(db: Session = Depends(get_db)):
    return StudentService.get_stats(db=db)


@router.get(
    "/import-template",
    summary="Download bulk import CSV template",
    description="Returns a sample CSV template with pre-populated 12-char roll numbers and demo rows.",
)
def download_import_template():
    sample_csv = (
        "roll_no,name,email,phone,department,section,academic_year,status\n"
        "2023PECIT410,Arun Kumar,arun@example.com,9876543210,Information Technology,A,2023-2027,active\n"
        "2023PECIT411,Priya Devi,priya@example.com,9876543211,Information Technology,A,2023-2027,active\n"
        "2023PECCSE101,Rahul Sharma,rahul@example.com,9876543212,Computer Science,B,2023-2027,active\n"
    )
    return Response(
        content=sample_csv,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=student_import_template.csv"},
    )


@router.post(
    "/bulk-delete",
    response_model=BulkDeleteResponse,
    summary="Bulk delete students",
    description="Deletes multiple student records by their UUIDs in an atomic transaction.",
)
def bulk_delete_students(
    payload: BulkDeleteRequest,
    db: Session = Depends(get_db),
):
    return StudentService.bulk_delete_students(db=db, student_ids=payload.student_ids)


@router.get(
    "/{student_id}",
    response_model=StudentResponse,
    summary="Get student by ID",
    description="Retrieve specific student details by UUID.",
)
def get_student(student_id: str, db: Session = Depends(get_db)):
    return StudentService.get_student_by_id(db=db, student_id=student_id)


@router.post(
    "",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new student",
    description="Add a new student record to the system with unique 12-character roll number.",
)
def create_student(student_in: StudentCreate, db: Session = Depends(get_db)):
    return StudentService.create_student(db=db, student_in=student_in)


@router.put(
    "/{student_id}",
    response_model=StudentResponse,
    summary="Update student details",
    description="Update an existing student's academic and personal details.",
)
def update_student(
    student_id: str,
    student_in: StudentUpdate,
    db: Session = Depends(get_db),
):
    return StudentService.update_student(db=db, student_id=student_id, student_in=student_in)


@router.delete(
    "/{student_id}",
    summary="Delete a student",
    description="Permanently delete a student record by ID.",
)
def delete_student(student_id: str, db: Session = Depends(get_db)):
    return StudentService.delete_student(db=db, student_id=student_id)


@router.post(
    "/import",
    response_model=BulkImportResponse,
    summary="Bulk import students from CSV or XLSX",
    description="Upload a CSV or Excel (.xlsx) file to batch import students with transaction safety and detailed row validation.",
)
async def bulk_import_students(
    file: UploadFile = File(..., description="CSV or XLSX spreadsheet containing student records"),
    db: Session = Depends(get_db),
):
    return await StudentService.bulk_import_students(db=db, file=file)
