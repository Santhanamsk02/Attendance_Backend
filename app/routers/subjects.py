from typing import Optional
from fastapi import APIRouter, Depends, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.database.database import get_db
from app.schemas.subject import (
    SubjectCreate,
    SubjectUpdate,
    SubjectResponse,
    SubjectListResponse,
    SubjectStatsResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkImportResponse,
)
from app.services.subject_service import SubjectService


router = APIRouter(prefix="/subjects", tags=["Subjects"])


@router.get(
    "",
    response_model=SubjectListResponse,
    summary="List subjects with pagination, search, and filters",
)
def list_subjects(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by code, name, or department"),
    department: Optional[str] = Query(None, description="Filter by department"),
    academic_year: Optional[str] = Query(None, description="Filter by academic year"),
    semester: Optional[int] = Query(None, ge=1, le=8, description="Filter by semester"),
    subject_type: Optional[str] = Query(None, description="Filter by type"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db),
):
    return SubjectService.get_subjects(
        db,
        page=page,
        limit=limit,
        search=search,
        department=department,
        academic_year=academic_year,
        semester=semester,
        subject_type=subject_type,
        status_filter=status_filter,
    )


@router.get(
    "/stats",
    response_model=SubjectStatsResponse,
    summary="Get subject statistics for the dashboard",
)
def get_stats(db: Session = Depends(get_db)):
    return SubjectService.get_stats(db)


@router.get(
    "/import-template",
    summary="Download a CSV template for bulk subject import",
)
def download_template():
    header = "subject_code,subject_name,subject_title,department,academic_year,semester,subject_type,credits,description,status\n"
    sample1 = "CS8391,DSA,Data Structures and Algorithms,CSE,2023-2024,3,Theory,3,Core data structures and algorithms,active\n"
    sample2 = "CS8381,DSA Lab,Data Structures Lab,CSE,2023-2024,3,Practical,2,Lab sessions for DS,active\n"
    csv_content = header + sample1 + sample2
    content = io.BytesIO(csv_content.encode("utf-8"))
    return StreamingResponse(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=subject_import_template.csv"},
    )


@router.get(
    "/{subject_id}",
    response_model=SubjectResponse,
    summary="Get a single subject by ID",
)
def get_subject(subject_id: str, db: Session = Depends(get_db)):
    subject = SubjectService.get_subject_by_id(db, subject_id)
    return SubjectResponse.model_validate(subject)


@router.post(
    "",
    response_model=SubjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new subject",
)
def create_subject(subject_in: SubjectCreate, db: Session = Depends(get_db)):
    return SubjectService.create_subject(db, subject_in)


@router.put(
    "/{subject_id}",
    response_model=SubjectResponse,
    summary="Update a subject",
)
def update_subject(
    subject_id: str, subject_in: SubjectUpdate, db: Session = Depends(get_db)
):
    return SubjectService.update_subject(db, subject_id, subject_in)


@router.delete(
    "/{subject_id}",
    summary="Delete a subject",
)
def delete_subject(subject_id: str, db: Session = Depends(get_db)):
    return SubjectService.delete_subject(db, subject_id)


@router.post(
    "/bulk",
    response_model=BulkDeleteResponse,
    summary="Bulk delete subjects",
)
def bulk_delete(body: BulkDeleteRequest, db: Session = Depends(get_db)):
    return SubjectService.bulk_delete_subjects(db, body.subject_ids)


@router.post(
    "/import",
    response_model=BulkImportResponse,
    summary="Bulk import subjects from CSV/XLSX",
)
async def import_subjects(
    file: UploadFile = File(..., description="CSV or XLSX file"),
    db: Session = Depends(get_db),
):
    return await SubjectService.bulk_import_subjects(db, file)
