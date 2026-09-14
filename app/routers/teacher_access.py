from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
import uuid

from app.database.database import get_db
from app.models.teacher import Teacher


router = APIRouter(prefix="/teacher-access", tags=["Teacher Access"])


class VerifyIdRequest(BaseModel):
    scanned_employee_id: str
    authenticated_employee_id: str  # In real JWT, this comes from token dependency


class VerifyIdResponse(BaseModel):
    verified: bool
    verification_token: str
    message: str


@router.post("/verify-id", response_model=VerifyIdResponse)
def verify_teacher_id(request: VerifyIdRequest, db: Session = Depends(get_db)):
    """
    Verifies that the scanned ID card belongs to the authenticated teacher.
    Since we are using mock JWT tokens in the frontend, the frontend passes both 
    for now. In a full production JWT setup, `authenticated_employee_id` would be 
    extracted by a FastAPI Depenedency (e.g. `get_current_user`).
    """
    # Verify the teacher exists
    teacher = db.query(Teacher).filter(Teacher.employee_id == request.authenticated_employee_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Authenticated teacher not found")

    # Match scanned ID against authenticated ID
    if request.scanned_employee_id != teacher.employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="The scanned faculty ID does not belong to your account."
        )

    # Issue verification session token
    # This token will be required by Attendance APIs
    verification_token = f"veri-token-{teacher.id}"
    
    return VerifyIdResponse(
        verified=True,
        verification_token=verification_token,
        message="Faculty ID Verified Successfully"
    )
