import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import HTTPException, status, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.teacher import Teacher
from app.models.department import Department
from app.schemas.teacher import (
    TeacherCreate,
    TeacherUpdate,
    TeacherResponse,
    TeacherListResponse,
    TeacherStatsResponse,
    BulkImportResponse,
    BulkDeleteResponse,
)
from app.utils.teacher_import import parse_teacher_uploaded_file, validate_and_sanitize_teacher_rows


class TeacherService:
    @staticmethod
    def get_teachers(
        db: Session,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        department: Optional[str] = None,
        status_filter: Optional[str] = None,
        designation: Optional[str] = None,
    ) -> TeacherListResponse:
        """
        Retrieves a paginated list of teachers with optional search and multiple filters.
        """
        query = db.query(Teacher)

        if search:
            search_term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Teacher.employee_id.ilike(search_term),
                    Teacher.name.ilike(search_term),
                    Teacher.email.ilike(search_term),
                    Teacher.phone.ilike(search_term),
                )
            )

        if department:
            query = query.filter(Teacher.department_id == department.strip())
        if status_filter:
            query = query.filter(Teacher.status == status_filter.strip().lower())
        if designation:
            search_desig = f"%{designation.strip().lower()}%"
            query = query.filter(func.lower(Teacher.designation).like(search_desig))

        total = query.count()
        total_pages = math.ceil(total / limit) if total > 0 else 1

        offset = (page - 1) * limit
        teachers = (
            query.order_by(Teacher.created_at.desc(), Teacher.employee_id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return TeacherListResponse(
            items=[TeacherResponse.model_validate(t) for t in teachers],
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        )

    @staticmethod
    def get_teacher_by_id(db: Session, teacher_id: str) -> Teacher:
        """
        Retrieves a teacher by UUID or raises a 404 error.
        """
        teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Teacher with ID '{teacher_id}' not found",
            )
        return teacher

    @staticmethod
    def create_teacher(db: Session, teacher_in: TeacherCreate) -> TeacherResponse:
        """
        Creates a new teacher record with uniqueness verification.
        """
        existing_emp = db.query(Teacher).filter(Teacher.employee_id == teacher_in.employee_id).first()
        if existing_emp:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Teacher with employee ID '{teacher_in.employee_id}' already exists",
            )

        if teacher_in.email:
            existing_email = db.query(Teacher).filter(Teacher.email == teacher_in.email).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Teacher with email '{teacher_in.email}' already exists",
                )

        teacher = Teacher(**teacher_in.model_dump())
        db.add(teacher)
        db.commit()
        db.refresh(teacher)
        return TeacherResponse.model_validate(teacher)

    @staticmethod
    def update_teacher(
        db: Session, teacher_id: str, teacher_in: TeacherUpdate
    ) -> TeacherResponse:
        """
        Updates an existing teacher with uniqueness checks for employee_id and email.
        """
        teacher = TeacherService.get_teacher_by_id(db, teacher_id)
        update_data = teacher_in.model_dump(exclude_unset=True)

        if "employee_id" in update_data and update_data["employee_id"] != teacher.employee_id:
            collision = (
                db.query(Teacher)
                .filter(Teacher.employee_id == update_data["employee_id"], Teacher.id != teacher_id)
                .first()
            )
            if collision:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Teacher with employee ID '{update_data['employee_id']}' already exists",
                )

        if "email" in update_data and update_data["email"]:
            collision = (
                db.query(Teacher)
                .filter(Teacher.email == update_data["email"], Teacher.id != teacher_id)
                .first()
            )
            if collision:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Teacher with email '{update_data['email']}' already exists",
                )

        for field, value in update_data.items():
            setattr(teacher, field, value)

        db.commit()
        db.refresh(teacher)
        return TeacherResponse.model_validate(teacher)

    @staticmethod
    def delete_teacher(db: Session, teacher_id: str) -> dict:
        """
        Deletes a teacher record from the database.
        """
        teacher = TeacherService.get_teacher_by_id(db, teacher_id)
        db.delete(teacher)
        db.commit()
        return {"message": "Teacher deleted successfully", "id": teacher_id}

    @staticmethod
    def get_stats(db: Session) -> TeacherStatsResponse:
        """
        Calculates teacher statistics for the Admin Dashboard.
        """
        total_teachers = db.query(func.count(Teacher.id)).scalar() or 0
        active_teachers = (
            db.query(func.count(Teacher.id)).filter(Teacher.status == "active").scalar() or 0
        )
        inactive_teachers = total_teachers - active_teachers
        departments_count = (
            db.query(func.count(func.distinct(Teacher.department_id))).scalar() or 0
        )

        return TeacherStatsResponse(
            total_teachers=total_teachers,
            active_teachers=active_teachers,
            inactive_teachers=inactive_teachers,
            departments=departments_count,
        )

    @staticmethod
    async def bulk_import_teachers(db: Session, file: UploadFile) -> BulkImportResponse:
        """
        Safely parses, validates, and batch inserts teachers with detailed error reporting.
        """
        raw_rows = await parse_teacher_uploaded_file(file)
        total_rows = len(raw_rows)

        if total_rows == 0:
            return BulkImportResponse(
                total_rows=0,
                successful=0,
                failed=0,
                errors=[],
            )

        existing_emps = {r[0] for r in db.query(Teacher.employee_id).all()}
        existing_emails = {
            e[0] for e in db.query(Teacher.email).filter(Teacher.email.isnot(None)).all()
        }

        # Build dynamic relational mapping for Departments
        all_depts = db.query(Department).all()
        departments_map = {}
        for d in all_depts:
            departments_map[d.name.lower()] = str(d.id)
            departments_map[d.code.lower()] = str(d.id)

        valid_teachers, errors = validate_and_sanitize_teacher_rows(
            raw_rows=raw_rows,
            existing_employee_ids=existing_emps,
            existing_emails=existing_emails,
            departments_map=departments_map,
        )

        successful_count = 0
        if valid_teachers:
            try:
                db_entities = [Teacher(**item.model_dump()) for item in valid_teachers]
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
    def bulk_delete_teachers(db: Session, teacher_ids: List[str]) -> BulkDeleteResponse:
        """
        Deletes multiple teacher records in an atomic transaction.
        Checks for non-existent IDs.
        """
        if not teacher_ids:
            return BulkDeleteResponse(deleted_count=0, message="No teacher IDs provided", not_found=0)

        try:
            existing = db.query(Teacher).filter(Teacher.id.in_(teacher_ids)).all()
            existing_ids = {str(t.id) for t in existing}
            requested_count = len(teacher_ids)
            not_found = requested_count - len(existing_ids)
            if existing_ids:
                db.query(Teacher).filter(Teacher.id.in_(existing_ids)).delete(synchronize_session=False)
                db.commit()

            return BulkDeleteResponse(
                deleted_count=len(existing_ids),
                message=f"Successfully deleted {len(existing_ids)} teacher(s)",
                not_found=not_found
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error during bulk deletion: {str(e)}",
            )
