import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import HTTPException, status, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.subject import Subject
from app.schemas.subject import (
    SubjectCreate,
    SubjectUpdate,
    SubjectResponse,
    SubjectListResponse,
    SubjectStatsResponse,
    BulkImportResponse,
    BulkDeleteResponse,
)
from app.utils.subject_import import parse_subject_uploaded_file, validate_and_sanitize_subject_rows


class SubjectService:
    @staticmethod
    def get_subjects(
        db: Session,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        department: Optional[str] = None,
        academic_year: Optional[str] = None,
        semester: Optional[int] = None,
        subject_type: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> SubjectListResponse:
        from app.models.department import Department
        query = db.query(Subject).join(Department, Subject.department_id == Department.id)

        if search:
            search_term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Subject.subject_code.ilike(search_term),
                    Subject.subject_name.ilike(search_term),
                    Subject.subject_title.ilike(search_term),
                    Department.code.ilike(search_term),
                    Department.name.ilike(search_term),
                )
            )

        if department:
            query = query.filter(func.lower(Department.code) == department.strip().lower())
        if academic_year:
            query = query.filter(Subject.academic_year == academic_year.strip())
        if semester is not None and semester > 0:
            query = query.filter(Subject.semester == semester)
        if subject_type:
            query = query.filter(func.lower(Subject.subject_type) == subject_type.strip().lower())
        if status_filter:
            query = query.filter(Subject.status == status_filter.strip().lower())

        total = query.count()
        total_pages = math.ceil(total / limit) if total > 0 else 1

        offset = (page - 1) * limit
        subjects = (
            query.order_by(Subject.created_at.desc(), Subject.subject_code.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return SubjectListResponse(
            items=[SubjectResponse.model_validate(s) for s in subjects],
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        )

    @staticmethod
    def get_subject_by_id(db: Session, subject_id: str) -> Subject:
        subject = db.query(Subject).filter(Subject.id == subject_id).first()
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subject with ID '{subject_id}' not found",
            )
        return subject

    @staticmethod
    def create_subject(db: Session, subject_in: SubjectCreate) -> SubjectResponse:
        existing = (
            db.query(Subject)
            .filter(
                func.lower(Subject.subject_code) == subject_in.subject_code.lower(),
                Subject.department_id == subject_in.department_id,
                Subject.academic_year == subject_in.academic_year,
                Subject.semester == subject_in.semester,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Subject code {subject_in.subject_code} already exists for this department, semester {subject_in.semester}, academic year {subject_in.academic_year}",
            )

        data = subject_in.model_dump()
        subject = Subject(**data)
        db.add(subject)
        db.commit()
        db.refresh(subject)
        return SubjectResponse.model_validate(subject)

    @staticmethod
    def update_subject(
        db: Session, subject_id: str, subject_in: SubjectUpdate
    ) -> SubjectResponse:
        subject = SubjectService.get_subject_by_id(db, subject_id)
        update_data = subject_in.model_dump(exclude_unset=True)

        new_code = update_data.get("subject_code", subject.subject_code)
        new_dept = update_data.get("department_id", subject.department_id)
        new_year = update_data.get("academic_year", subject.academic_year)
        new_sem = update_data.get("semester", subject.semester)

        if (new_code != subject.subject_code or new_dept != subject.department_id or
                new_year != subject.academic_year or new_sem != subject.semester):
            collision = (
                db.query(Subject)
                .filter(
                    func.lower(Subject.subject_code) == new_code.lower(),
                    Subject.department_id == new_dept,
                    Subject.academic_year == new_year,
                    Subject.semester == new_sem,
                    Subject.id != subject_id,
                )
                .first()
            )
            if collision:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Subject code {new_code} already exists for this department, semester {new_sem}, academic year {new_year}",
                )

        for field, value in update_data.items():
            setattr(subject, field, value)

        db.commit()
        db.refresh(subject)
        return SubjectResponse.model_validate(subject)

    @staticmethod
    def delete_subject(db: Session, subject_id: str) -> dict:
        subject = SubjectService.get_subject_by_id(db, subject_id)
        db.delete(subject)
        db.commit()
        return {"message": "Subject deleted successfully", "id": subject_id}

    @staticmethod
    def get_stats(db: Session) -> SubjectStatsResponse:
        total = db.query(func.count(Subject.id)).scalar() or 0
        active = db.query(func.count(Subject.id)).filter(Subject.status == "active").scalar() or 0
        inactive = total - active
        departments = db.query(func.count(func.distinct(Subject.department_id))).scalar() or 0

        return SubjectStatsResponse(
            total_subjects=total,
            active_subjects=active,
            inactive_subjects=inactive,
            departments=departments,
        )

    @staticmethod
    async def bulk_import_subjects(db: Session, file: UploadFile) -> BulkImportResponse:
        raw_rows = await parse_subject_uploaded_file(file)
        total_rows = len(raw_rows)

        if total_rows == 0:
            return BulkImportResponse(total_rows=0, successful=0, failed=0, errors=[])

        # Get existing composites for duplicate checks
        existing_composites = set()
        for row in db.query(
            Subject.subject_code, Subject.department_id, Subject.academic_year, Subject.semester
        ).all():
            existing_composites.add(
                (row[0].upper(), str(row[1]), row[2], row[3])
            )

        from app.models.department import Department
        from app.models.batch import Batch

        departments = db.query(Department).all()
        departments_map = {str(d.code.upper()): str(d.id) for d in departments}
        for d in departments:
            departments_map[str(d.name.upper())] = str(d.id)

        batches = db.query(Batch).all()
        batches_map = {}
        for b in batches:
            if b.department_id not in batches_map:
                batches_map[b.department_id] = {}
            batches_map[b.department_id][str(b.batch_name.upper())] = b

        valid_subjects, errors = validate_and_sanitize_subject_rows(
            raw_rows=raw_rows,
            existing_composites=existing_composites,
            departments_map=departments_map,
            batches_map=batches_map,
        )

        successful_count = 0
        if valid_subjects:
            try:
                db_entities = [Subject(**item.model_dump()) for item in valid_subjects]
                db.add_all(db_entities)
                db.commit()
                successful_count = len(db_entities)
            except Exception as e:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Database error during bulk insertion: {str(e)}",
                )

        return BulkImportResponse(
            total_rows=total_rows,
            successful=successful_count,
            failed=len(errors),
            errors=errors,
        )

    @staticmethod
    def bulk_delete_subjects(db: Session, subject_ids: List[str]) -> BulkDeleteResponse:
        if not subject_ids:
            return BulkDeleteResponse(deleted_count=0, message="No subject IDs provided", not_found=0)

        try:
            existing = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
            existing_ids = {str(s.id) for s in existing}
            not_found = len(subject_ids) - len(existing_ids)
            if existing_ids:
                db.query(Subject).filter(Subject.id.in_(existing_ids)).delete(synchronize_session=False)
                db.commit()

            return BulkDeleteResponse(
                deleted_count=len(existing_ids),
                message=f"Successfully deleted {len(existing_ids)} subject(s)",
                not_found=not_found,
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error during bulk deletion: {str(e)}",
            )
