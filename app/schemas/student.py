import re
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudentBase(BaseModel):
    roll_no: str = Field(
        ...,
        min_length=3,
        max_length=30,
        description="Unique student roll number (e.g. 2023PECIT410, 2023PECCSE100, 2023PECAIDS230)",
    )
    name: str = Field(..., min_length=2, max_length=150, description="Full Student Name")
    email: Optional[str] = Field(None, max_length=255, description="Student Email Address")
    phone: Optional[str] = Field(None, max_length=30, description="Contact Phone Number")
    department_id: str = Field(..., min_length=1, max_length=100, description="Department ID")
    batch_id: str = Field(..., min_length=1, max_length=100, description="Batch ID")
    semester: int = Field(..., ge=1, le=8, description="Current Semester (1-8)")
    section: str = Field(..., min_length=1, max_length=20, description="Class Section (e.g. A to Z, A1, B)")
    academic_year: str = Field(..., min_length=4, max_length=20, description="Academic Year / Batch (e.g. 2023-2027)")
    status: str = Field("active", description="Status: 'active' or 'inactive'")

    @field_validator("roll_no", mode="before")
    @classmethod
    def clean_roll_no(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().upper()
            if len(v) < 3:
                raise ValueError("Roll number must be at least 3 characters")
            if not re.match(r"^[A-Z0-9\-_/]+$", v):
                raise ValueError("Roll number must contain only letters, numbers, hyphens, or underscores")
        return v

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Student name must be at least 2 characters")
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

    @field_validator("section", mode="before")
    @classmethod
    def clean_section(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().upper()
            if not v:
                raise ValueError("Section cannot be blank")
        return v

    @field_validator("department_id", "academic_year", mode="before")
    @classmethod
    def clean_strings(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Field cannot be blank")
        return v

    @field_validator("status", mode="before")
    @classmethod
    def clean_status(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in ("active", "inactive"):
                raise ValueError("Status must be either 'active' or 'inactive'")
        return v


class StudentCreate(StudentBase):
    pass


class StudentUpdate(BaseModel):
    roll_no: Optional[str] = Field(None, min_length=3, max_length=30)
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
    department_id: Optional[str] = Field(None, min_length=1, max_length=100)
    batch_id: Optional[str] = Field(None, min_length=1, max_length=100)
    semester: Optional[int] = Field(None, ge=1, le=8)
    section: Optional[str] = Field(None, min_length=1, max_length=20)
    academic_year: Optional[str] = Field(None, min_length=4, max_length=20)
    status: Optional[str] = Field(None)

    @field_validator("roll_no", mode="before")
    @classmethod
    def clean_roll_no(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and isinstance(v, str):
            v = v.strip().upper()
            if len(v) < 3:
                raise ValueError("Roll number must be at least 3 characters")
            if not re.match(r"^[A-Z0-9\-_/]+$", v):
                raise ValueError("Roll number must contain only letters, numbers, hyphens, or underscores")
        return v

    @field_validator("section", mode="before")
    @classmethod
    def clean_section(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and isinstance(v, str):
            v = v.strip().upper()
            if not v:
                raise ValueError("Section cannot be blank")
        return v

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and isinstance(v, str):
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Student name must be at least 2 characters")
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
class DepartmentNestedResponse(BaseModel):
    id: str
    name: str
    code: str
    
    model_config = ConfigDict(from_attributes=True)


class StudentResponse(StudentBase):
    id: str
    created_at: datetime
    updated_at: datetime
    department: Optional[DepartmentNestedResponse] = Field(None, validation_alias="department_rel")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class StudentListResponse(BaseModel):
    items: List[StudentResponse]
    page: int
    limit: int
    total: int
    total_pages: int


class StudentStatsResponse(BaseModel):
    total_students: int
    active_students: int
    recently_added: int
    departments: int


class ImportErrorItem(BaseModel):
    row: int
    roll_no: Optional[str] = None
    error: str


class BulkImportResponse(BaseModel):
    total_rows: int
    successful: int
    failed: int
    errors: List[ImportErrorItem]


class BulkDeleteRequest(BaseModel):
    student_ids: List[str] = Field(..., min_length=1, description="List of student IDs to delete")


class BulkDeleteResponse(BaseModel):
    deleted_count: int
    message: str
