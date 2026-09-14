from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid

from app.database.database import get_db
from app.schemas.auth import LoginRequest, LoginResponse
from app.models.admin import Admin
from app.models.teacher import Teacher

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    # 1. Check Admin
    admin = db.query(Admin).filter(Admin.email == request.email).first()
    if admin:
        if admin.password == request.password:
            return LoginResponse(
                token=f"mock-jwt-admin-{uuid.uuid4()}",
                role="admin",
                user_info={"name": admin.name, "email": admin.email}
            )
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    
    # 2. Check Teacher
    teacher = db.query(Teacher).filter(Teacher.email == request.email).first()
    if teacher:
        if teacher.employee_id == request.password:
            if teacher.status != "active":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher account is inactive")
                
            return LoginResponse(
                token=f"mock-jwt-teacher-{teacher.id}",
                role="teacher",
                user_info={"name": teacher.name, "email": teacher.email, "employee_id": teacher.employee_id}
            )
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
            
    # Neither
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found. Please verify your email.")
