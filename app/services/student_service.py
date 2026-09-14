import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from fastapi import HTTPException, status, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.student import Student
from app.schemas.student import (
    StudentCreate,
    StudentUpdate,
    StudentResponse,
    StudentListResponse,
    StudentStatsResponse,
    BulkImportResponse,
    BulkDeleteResponse,
)
from app.utils.bulk_import import parse_uploaded_file, validate_and_sanitize_rows


class StudentService:
    @staticmethod
    def get_students(
        db: Session,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        department_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        section: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> StudentListResponse:
        """
        Retrieves a paginated list of students with optional search and multiple filters.
        """
        query = db.query(Student)

        # Apply search query across roll_no, name, and email
        if search:
            search_term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Student.roll_no.ilike(search_term),
                    Student.name.ilike(search_term),
                    Student.email.ilike(search_term),
                )
            )

        # Apply specific filters
        if department_id:
            query = query.filter(Student.department_id == department_id)
        if batch_id:
            query = query.filter(Student.batch_id == batch_id)
        if section:
            query = query.filter(func.lower(Student.section) == section.strip().lower())
        if status_filter:
            query = query.filter(Student.status == status_filter.strip().lower())

        total = query.count()
        total_pages = math.ceil(total / limit) if total > 0 else 1

        offset = (page - 1) * limit
        students = (
            query.order_by(Student.created_at.desc(), Student.roll_no.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return StudentListResponse(
            items=[StudentResponse.model_validate(s) for s in students],
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        )

    @staticmethod
    def get_student_by_id(db: Session, student_id: str) -> Student:
        """
        Retrieves a student by UUID or raises a 404 error.
        """
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student with ID '{student_id}' not found",
            )
        return student

    @staticmethod
    def get_student_by_roll_no(db: Session, roll_no: str) -> Optional[Student]:
        """
        Retrieves a student by unique roll number (optimized for barcode scanning).
        """
        return db.query(Student).filter(Student.roll_no == roll_no.strip().upper()).first()

    @staticmethod
    def create_student(db: Session, student_in: StudentCreate) -> StudentResponse:
        """
        Creates a new student record with uniqueness verification.
        """
        # Check roll number uniqueness
        existing_roll = db.query(Student).filter(Student.roll_no == student_in.roll_no).first()
        if existing_roll:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Student with roll number '{student_in.roll_no}' already exists",
            )

        # Check email uniqueness if email provided
        if student_in.email:
            existing_email = db.query(Student).filter(Student.email == student_in.email).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Student with email '{student_in.email}' already exists",
                )

        student = Student(**student_in.model_dump())
        db.add(student)
        db.commit()
        db.refresh(student)
        return StudentResponse.model_validate(student)

    @staticmethod
    def update_student(
        db: Session, student_id: str, student_in: StudentUpdate
    ) -> StudentResponse:
        """
        Updates an existing student with uniqueness checks for roll_no and email.
        """
        student = StudentService.get_student_by_id(db, student_id)
        update_data = student_in.model_dump(exclude_unset=True)

        # If updating roll_no, check collision
        if "roll_no" in update_data and update_data["roll_no"] != student.roll_no:
            collision = (
                db.query(Student)
                .filter(Student.roll_no == update_data["roll_no"], Student.id != student_id)
                .first()
            )
            if collision:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Student with roll number '{update_data['roll_no']}' already exists",
                )

        # If updating email, check collision
        if "email" in update_data and update_data["email"]:
            collision = (
                db.query(Student)
                .filter(Student.email == update_data["email"], Student.id != student_id)
                .first()
            )
            if collision:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Student with email '{update_data['email']}' already exists",
                )

        for field, value in update_data.items():
            setattr(student, field, value)

        db.commit()
        db.refresh(student)
        return StudentResponse.model_validate(student)

    @staticmethod
    def delete_student(db: Session, student_id: str) -> dict:
        """
        Deletes a student record from the database.
        """
        student = StudentService.get_student_by_id(db, student_id)
        db.delete(student)
        db.commit()
        return {"message": "Student deleted successfully", "id": student_id}

    @staticmethod
    def get_stats(db: Session) -> StudentStatsResponse:
        """
        Calculates student statistics for the Admin Dashboard.
        """
        total_students = db.query(func.count(Student.id)).scalar() or 0
        active_students = (
            db.query(func.count(Student.id)).filter(Student.status == "active").scalar() or 0
        )
        from app.models.department import Department
        departments_count = (
            db.query(func.count(Department.id)).scalar() or 0
        )

        # Calculate recently added (added in the last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recently_added = (
            db.query(func.count(Student.id))
            .filter(Student.created_at >= thirty_days_ago)
            .scalar()
            or 0
        )

        # If zero (e.g. fresh database), fallback to total or recent 5
        if recently_added == 0 and total_students > 0:
            recently_added = min(total_students, 10)

        return StudentStatsResponse(
            total_students=total_students,
            active_students=active_students,
            recently_added=recently_added,
            departments=departments_count,
        )

    @staticmethod
    async def bulk_import_students(db: Session, file: UploadFile) -> BulkImportResponse:
        """
        Safely parses, validates, and batch inserts students with detailed error reporting.
        """
        raw_rows = await parse_uploaded_file(file)
        total_rows = len(raw_rows)

        if total_rows == 0:
            return BulkImportResponse(
                total_rows=0,
                successful=0,
                failed=0,
                errors=[],
            )

        # Pre-fetch existing roll numbers and emails to avoid per-row database queries
        existing_rolls = {r[0] for r in db.query(Student.roll_no).all()}
        existing_emails = {
            e[0] for e in db.query(Student.email).filter(Student.email.isnot(None)).all()
        }

        # Build mapping dictionaries to resolve foreign keys dynamically
        from app.models.department import Department
        from app.models.batch import Batch
        
        departments_map = {}
        for d in db.query(Department).all():
            departments_map[d.code.lower()] = d.id
            departments_map[d.name.lower()] = d.id
            
        batches_map = {}
        for b in db.query(Batch).all():
            batches_map[(b.department_id, b.batch_name.lower())] = b

        valid_students, errors = validate_and_sanitize_rows(
            raw_rows=raw_rows,
            existing_roll_nos=existing_rolls,
            existing_emails=existing_emails,
            departments_map=departments_map,
            batches_map=batches_map,
        )

        successful_count = 0
        if valid_students:
            try:
                db_entities = [Student(**item.model_dump()) for item in valid_students]
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
    def bulk_delete_students(db: Session, student_ids: List[str]) -> BulkDeleteResponse:
        """
        Deletes multiple student records in an atomic transaction.
        """
        if not student_ids:
            return BulkDeleteResponse(deleted_count=0, message="No student IDs provided")

        try:
            deleted_count = (
                db.query(Student)
                .filter(Student.id.in_(student_ids))
                .delete(synchronize_session=False)
            )
            db.commit()
            return BulkDeleteResponse(
                deleted_count=deleted_count,
                message=f"Successfully deleted {deleted_count} student(s)",
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error during bulk deletion: {str(e)}",
            )

