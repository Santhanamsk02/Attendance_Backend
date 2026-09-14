import re
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TeacherBase(BaseModel):
    employee_id: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Unique employee ID (e.g. EMP001)",
    )
    name: str = Field(..., min_length=2, max_length=150, description="Full Teacher Name")
    email: Optional[str] = Field(None, max_length=255, description="Teacher Email Address")
    phone: Optional[str] = Field(None, max_length=30, description="Contact Phone Number")
    department_id: str = Field(..., min_length=1, max_length=100, description="Department ID")
    designation: Optional[str] = Field(None, max_length=100, description="Job Designation")
    status: str = Field("active", description="Status: 'active' or 'inactive'")

    @field_validator("employee_id", mode="before")
    @classmethod
    def clean_employee_id(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().upper()
            if len(v) < 2:
                raise ValueError("Employee ID must be at least 2 characters")
        return v

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Teacher name must be at least 2 characters")
        return v

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and isinstance(v, str):
            v = v.strip().lower()
            if not v:
                return None
            email_pattern = r"^[^@]+@[^@]+\.[^@]+$"
            if not re.match(email_pattern, v):
                raise ValueError("Invalid email format")
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def clean_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and isinstance(v, str):
            v = v.strip()
            if not v:
                return None
            cleaned = re.sub(r"[\s\-\(\)\+]", "", v)
            if not cleaned.isalnum() or len(cleaned) < 5:
                raise ValueError("Invalid phone number format")
        return v

    @field_validator("status", mode="before")
    @classmethod
    def clean_status(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in ("active", "inactive"):
                raise ValueError("Status must be either 'active' or 'inactive'")
        return v


class TeacherCreate(TeacherBase):
    pass


class TeacherUpdate(BaseModel):
    employee_id: Optional[str] = Field(None, min_length=2, max_length=50)
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
    department_id: Optional[str] = Field(None, min_length=1, max_length=100)
    designation: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = Field(None)

    @field_validator("employee_id", mode="before")
    @classmethod
    def clean_employee_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and isinstance(v, str):
            v = v.strip().upper()
            if len(v) < 2:
                raise ValueError("Employee ID must be at least 2 characters")
        return v

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and isinstance(v, str):
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Teacher name must be at least 2 characters")
        return v

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and isinstance(v, str):
            v = v.strip().lower()
            if not v:
                return None
            email_pattern = r"^[^@]+@[^@]+\.[^@]+$"
            if not re.match(email_pattern, v):
                raise ValueError("Invalid email format")
        return v

    @field_validator("status", mode="before")
    @classmethod
    def clean_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and isinstance(v, str):
            v = v.strip().lower()
            if v not in ("active", "inactive"):
                raise ValueError("Status must be either 'active' or 'inactive'")
        return v


        return v


class DepartmentNestedResponse(BaseModel):
    id: str
    name: str
    code: str
    
    model_config = ConfigDict(from_attributes=True)


class TeacherResponse(TeacherBase):
    id: str
    created_at: datetime
    updated_at: datetime
    department: Optional[DepartmentNestedResponse] = Field(None, validation_alias="department_rel")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TeacherListResponse(BaseModel):
    items: List[TeacherResponse]
    page: int
    limit: int
    total: int
    total_pages: int


class TeacherStatsResponse(BaseModel):
    total_teachers: int
    active_teachers: int
    inactive_teachers: int
    departments: int


class ImportErrorItem(BaseModel):
    row: int
    employee_id: Optional[str] = None
    error: str


class BulkImportResponse(BaseModel):
    total_rows: int
    successful: int
    failed: int
    errors: List[ImportErrorItem]


class BulkDeleteRequest(BaseModel):
    teacher_ids: List[str] = Field(..., min_length=1, description="List of teacher IDs to delete")


class BulkDeleteResponse(BaseModel):
    deleted_count: int
    message: str
    not_found: int
