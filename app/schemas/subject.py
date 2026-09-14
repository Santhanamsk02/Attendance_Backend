import re
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_SUBJECT_TYPES = ("theory", "practical", "laboratory", "elective", "project", "other")


class SubjectBase(BaseModel):
    subject_code: str = Field(
        ..., min_length=2, max_length=20, description="Subject code (e.g. IT501)"
    )
    subject_name: str = Field(
        ..., min_length=1, max_length=200, description="Short subject name (e.g. DSA)"
    )
    subject_title: Optional[str] = Field(
        None, min_length=2, max_length=255, description="Full subject title (e.g. Data Structures and Algorithms)"
    )
    department_id: str = Field(
        ..., min_length=1, max_length=100, description="Department ID"
    )
    academic_year: str = Field(
        ..., min_length=4, max_length=20, description="Academic year (e.g. 2026-2027)"
    )
    semester: int = Field(
        ..., ge=1, le=8, description="Semester (1-8)"
    )
    subject_type: str = Field(
        ..., description="Type: theory, practical, laboratory, elective, project, other"
    )
    credits: Optional[int] = Field(
        None, ge=0, le=10, description="Credits (0-10)"
    )
    status: str = Field("active", description="Status: active or inactive")
    description: Optional[str] = Field(None, max_length=1000, description="Description")

    @field_validator("subject_code", mode="before")
    @classmethod
    def clean_subject_code(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().upper()
            if len(v) < 2:
                raise ValueError("Subject code must be at least 2 characters")
        return v

    @field_validator("subject_title", mode="before")
    @classmethod
    def clean_subject_title(cls, v: str) -> str:
        if v and isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("subject_name", mode="before")
    @classmethod
    def clean_subject_name(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Subject name is required")
        return v

    @field_validator("department_id", mode="before")
    @classmethod
    def clean_department_id(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("academic_year", mode="before")
    @classmethod
    def clean_academic_year(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not re.match(r"^\d{4}-\d{4}$", v):
                raise ValueError("Academic year must be in format YYYY-YYYY (e.g. 2026-2027)")
        return v

    @field_validator("subject_type", mode="before")
    @classmethod
    def clean_subject_type(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in VALID_SUBJECT_TYPES:
                raise ValueError(
                    f"Subject type must be one of: {', '.join(VALID_SUBJECT_TYPES)}"
                )
        return v

    @field_validator("status", mode="before")
    @classmethod
    def clean_status(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in ("active", "inactive"):
                raise ValueError("Status must be either 'active' or 'inactive'")
        return v


class SubjectCreate(SubjectBase):
    pass


class SubjectUpdate(BaseModel):
    subject_code: Optional[str] = Field(None, min_length=2, max_length=20)
    subject_name: Optional[str] = Field(None, min_length=1, max_length=200)
    subject_title: Optional[str] = Field(None, min_length=2, max_length=255)
    department_id: Optional[str] = Field(None, min_length=1, max_length=100)
    academic_year: Optional[str] = Field(None, min_length=4, max_length=20)
    semester: Optional[int] = Field(None, ge=1, le=8)
    subject_type: Optional[str] = Field(None)
    credits: Optional[int] = Field(None, ge=0, le=10)
    status: Optional[str] = Field(None)
    description: Optional[str] = Field(None, max_length=1000)

    @field_validator("subject_code", mode="before")
    @classmethod
    def clean_subject_code(cls, v):
        if v is not None and isinstance(v, str):
            v = v.strip().upper()
            if len(v) < 2:
                raise ValueError("Subject code must be at least 2 characters")
        return v

    @field_validator("subject_title", mode="before")
    @classmethod
    def clean_subject_title(cls, v):
        if v is not None and isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("subject_name", mode="before")
    @classmethod
    def clean_subject_name(cls, v):
        if v is not None and isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Subject name cannot be empty")
        return v

    @field_validator("academic_year", mode="before")
    @classmethod
    def clean_academic_year(cls, v):
        if v is not None and isinstance(v, str):
            v = v.strip()
            if not re.match(r"^\d{4}-\d{4}$", v):
                raise ValueError("Academic year must be in format YYYY-YYYY")
        return v

    @field_validator("subject_type", mode="before")
    @classmethod
    def clean_subject_type(cls, v):
        if v is not None and isinstance(v, str):
            v = v.strip().lower()
            if v not in VALID_SUBJECT_TYPES:
                raise ValueError(
                    f"Subject type must be one of: {', '.join(VALID_SUBJECT_TYPES)}"
                )
        return v

    @field_validator("status", mode="before")
    @classmethod
    def clean_status(cls, v):
        if v is not None and isinstance(v, str):
            v = v.strip().lower()
            if v not in ("active", "inactive"):
                raise ValueError("Status must be either 'active' or 'inactive'")
        return v


class DepartmentNestedResponse(BaseModel):
    id: str
    name: str
    code: str

    model_config = ConfigDict(from_attributes=True)


class SubjectResponse(SubjectBase):
    id: str
    department_id: Optional[str] = None
    department: Optional[DepartmentNestedResponse] = Field(None, validation_alias="department_rel")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class SubjectListResponse(BaseModel):
    items: List[SubjectResponse]
    page: int
    limit: int
    total: int
    total_pages: int


class SubjectStatsResponse(BaseModel):
    total_subjects: int
    active_subjects: int
    inactive_subjects: int
    departments: int


class ImportErrorItem(BaseModel):
    row: int
    subject_code: Optional[str] = None
    error: str


class BulkImportResponse(BaseModel):
    total_rows: int
    successful: int
    failed: int
    errors: List[ImportErrorItem]


class BulkDeleteRequest(BaseModel):
    subject_ids: List[str] = Field(..., min_length=1, description="List of subject IDs to delete")


class BulkDeleteResponse(BaseModel):
    deleted_count: int
    message: str
    not_found: int
