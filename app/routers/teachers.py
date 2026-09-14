from typing import Optional
from fastapi import APIRouter, Depends, Query, status, UploadFile, File, Response
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.teacher import (
    TeacherCreate,
    TeacherUpdate,
    TeacherResponse,
    TeacherListResponse,
    TeacherStatsResponse,
    BulkImportResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
)
from app.services.teacher_service import TeacherService

router = APIRouter(prefix="/teachers", tags=["Teachers"])


@router.get(
    "",
    response_model=TeacherListResponse,
    summary="Get paginated list of teachers",
    description="Retrieve teachers with optional search across employee ID, name, email and dynamic filters.",
)
@router.get(
    "/",
    response_model=TeacherListResponse,
    include_in_schema=False
)
def get_teachers(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(100, ge=1, le=500, description="Items per page"),

    search: Optional[str] = Query(None, description="Search term for employee_id, name, or email"),
    department: Optional[str] = Query(None, description="Filter by department"),
    status: Optional[str] = Query(None, description="Filter by status ('active' | 'inactive')"),
    designation: Optional[str] = Query(None, description="Filter by designation"),
    db: Session = Depends(get_db),
):
    return TeacherService.get_teachers(
        db=db,
        page=page,
        limit=limit,
        search=search,
        department=department,
        status_filter=status,
        designation=designation,
    )


@router.get(
    "/stats",
    response_model=TeacherStatsResponse,
    summary="Get teacher statistics",
    description="Retrieve summary statistics for the Admin Dashboard (total, active, inactive, departments).",
)
def get_teacher_stats(db: Session = Depends(get_db)):
    return TeacherService.get_stats(db=db)


@router.get(
    "/import-template",
    summary="Download bulk import CSV template for teachers",
    description="Returns a sample CSV template with pre-populated demo rows.",
)
def download_import_template():
    sample_csv = (
        "employee_id,name,email,phone,department,designation,status\n"
        "EMP001,Dr. Kumar,kumar@example.com,9876543210,IT,Assistant Professor,active\n"
        "EMP002,Dr. Priya,priya@example.com,9876543211,IT,Professor,active\n"
    )
    return Response(
        content=sample_csv,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=teacher_import_template.csv"},
    )


@router.post(
    "/bulk",
    response_model=BulkDeleteResponse,
    summary="Bulk delete teachers",
    description="Deletes multiple teacher records by their UUIDs in an atomic transaction.",
)
def bulk_delete_teachers(
    payload: BulkDeleteRequest,
    db: Session = Depends(get_db),
):
    return TeacherService.bulk_delete_teachers(db=db, teacher_ids=payload.teacher_ids)


@router.get(
    "/{teacher_id}",
    response_model=TeacherResponse,
    summary="Get teacher by ID",
    description="Retrieve specific teacher details by UUID.",
)
def get_teacher(teacher_id: str, db: Session = Depends(get_db)):
    return TeacherService.get_teacher_by_id(db=db, teacher_id=teacher_id)


@router.post(
    "",
    response_model=TeacherResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new teacher",
    description="Add a new teacher record to the system.",
)
def create_teacher(teacher_in: TeacherCreate, db: Session = Depends(get_db)):
    return TeacherService.create_teacher(db=db, teacher_in=teacher_in)


@router.put(
    "/{teacher_id}",
    response_model=TeacherResponse,
    summary="Update teacher details",
    description="Update an existing teacher's details.",
)
def update_teacher(
    teacher_id: str,
    teacher_in: TeacherUpdate,
    db: Session = Depends(get_db),
):
    return TeacherService.update_teacher(db=db, teacher_id=teacher_id, teacher_in=teacher_in)


@router.delete(
    "/{teacher_id}",
    summary="Delete a teacher",
    description="Permanently delete a teacher record by ID.",
)
def delete_teacher(teacher_id: str, db: Session = Depends(get_db)):
    return TeacherService.delete_teacher(db=db, teacher_id=teacher_id)


@router.post(
    "/import",
    response_model=BulkImportResponse,
    summary="Bulk import teachers from CSV or XLSX",
    description="Upload a CSV or Excel (.xlsx) file to batch import teachers with transaction safety and detailed row validation.",
)
async def bulk_import_teachers(
    file: UploadFile = File(..., description="CSV or XLSX spreadsheet containing teacher records"),
    db: Session = Depends(get_db),
):
    return await TeacherService.bulk_import_teachers(db=db, file=file)
