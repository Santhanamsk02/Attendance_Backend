from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date

from app.database.database import get_db
from app.models.attendance import AttendanceSession, SessionStatus, AttendanceMark, ScanMethod
from app.models.day_wise_attendance import DayWiseAttendance
from app.models.student import Student
from app.models.subject import Subject
from app.models.teacher import Teacher

router = APIRouter(prefix="/attendance", tags=["Attendance API"])

# -------------
# Schemas
# -------------
class StartSessionRequest(BaseModel):
    subject_code: str
    section_name: str
    period_id: str
    date: date

class SessionResponse(BaseModel):
    id: str
    status: str
    subject_code: str
    section_name: str
    period_id: str
    date: date
    created_at: datetime
    marked_rolls: List[str] = []
    
class ScanStudentRequest(BaseModel):
    roll_number: str
    method: ScanMethod

class SubmitSessionRequest(BaseModel):
    roll_numbers: List[str]

class MarkResponse(BaseModel):
    success: bool
    student_name: str
    roll_number: str
    method: str
    message: str

# -------------
# Dependencies
# -------------
def verify_teacher_session(teacher_verification_token: Optional[str] = Header(None)):
    if not teacher_verification_token or not teacher_verification_token.startswith("veri-token-"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid Teacher Verification Token is required to access Attendance systems."
        )
    return teacher_verification_token.split("veri-token-")[1]

# -------------
# Endpoints
# -------------

@router.post("/sessions", response_model=SessionResponse)
def start_attendance_session(
    request: StartSessionRequest, 
    token: str = Depends(verify_teacher_session),
    db: Session = Depends(get_db)
):
    subj = db.query(Subject).filter(
        (Subject.subject_code == request.subject_code) | (Subject.id == request.subject_code)
    ).first()
    subject_id = subj.id if subj else ("ENTRY" if request.subject_code == "ENTRY" else request.subject_code)
    code = subj.subject_code if subj else request.subject_code

    teacher_id = token 
    
    from app.models.timetable import TeacherAssignment
    day_mapping = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}
    dow = day_mapping[request.date.weekday()]
    
    assignment = db.query(TeacherAssignment).filter(
        TeacherAssignment.teacher_id == teacher_id,
        TeacherAssignment.section_id == request.section_name,
        TeacherAssignment.period_id == request.period_id,
        TeacherAssignment.day_of_week == dow
    ).first()

    dept_id = assignment.department_id if assignment else (subj.department_id if subj else None)
    
    if not dept_id and request.subject_code == "ENTRY":
        teacher_obj = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if teacher_obj:
            dept_id = teacher_obj.department_id

    existing_session = db.query(AttendanceSession).filter(
        AttendanceSession.date == request.date,
        AttendanceSession.period_id == request.period_id,
        AttendanceSession.section_id == request.section_name,
        AttendanceSession.subject_id == subject_id,
        AttendanceSession.department_id == dept_id
    ).first()

    if existing_session:
        marks = db.query(AttendanceMark).filter(AttendanceMark.session_id == existing_session.id).all()
        setattr(existing_session, 'marked_rolls', [m.roll_number for m in marks])
        setattr(existing_session, 'subject_code', code)
        setattr(existing_session, 'section_name', existing_session.section_id or request.section_name)
        return existing_session

    # dept_id already calculated above

    batch_id = assignment.batch_id if assignment else None
    ay_id = assignment.academic_year_id if assignment else None
    sem = assignment.semester if assignment else (subj.semester if subj else None)
    
    new_session = AttendanceSession(
        teacher_id=teacher_id,
        subject_id=subject_id,
        section_id=request.section_name,
        date=request.date,
        period_id=request.period_id,
        status=SessionStatus.ACTIVE,
        department_id=dept_id,
        batch_id=batch_id,
        academic_year_id=ay_id,
        semester=sem
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    setattr(new_session, 'marked_rolls', [])
    setattr(new_session, 'subject_code', code)
    setattr(new_session, 'section_name', new_session.section_id or request.section_name)
    return new_session


@router.post("/sessions/{session_id}/submit")
def submit_attendance_session(
    session_id: str,
    request: SubmitSessionRequest,
    token: str = Depends(verify_teacher_session),
    db: Session = Depends(get_db)
):
    db_session = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Attendance session not found.")
    
    db.query(AttendanceMark).filter(AttendanceMark.session_id == session_id).delete()

    processed_rolls = set(request.roll_numbers)
    
    is_morning_entry = (db_session.period_id == "morning-entry" or db_session.subject_id is None)
    if is_morning_entry:
        db.query(DayWiseAttendance).filter(
            DayWiseAttendance.date == db_session.date,
            DayWiseAttendance.marked_by == token
        ).delete()

    added_count = 0
    for roll in processed_rolls:
        student = db.query(Student).filter(Student.roll_no == roll).first()
        if not student:
            continue
            
        new_mark = AttendanceMark(
            session_id=session_id,
            student_id=student.id,
            roll_number=student.roll_no,
            method=ScanMethod.MANUAL_ENTRY
        )
        db.add(new_mark)
        
        if is_morning_entry:
            new_day_mark = DayWiseAttendance(
                student_id=student.id,
                date=db_session.date,
                method=ScanMethod.MANUAL_ENTRY,
                marked_by=token
            )
            db.add(new_day_mark)
            
        added_count += 1

    db_session.status = SessionStatus.COMPLETED
    db_session.completed_at = datetime.utcnow()
    db.commit()
    
    return {"success": True, "message": f"Attendance finalized successfully. {added_count} students marked present."}

class SessionHistoryResponse(BaseModel):
    id: str
    date: str
    subject: str
    code: str
    section: str
    time: str
    present: int
    total: int
    status: str

@router.get("/sessions/history", response_model=List[SessionHistoryResponse])
def get_attendance_history(
    token: str = Depends(verify_teacher_session),
    db: Session = Depends(get_db)
):
    teacher_id = token
    sessions = db.query(AttendanceSession).filter(
        AttendanceSession.teacher_id == teacher_id,
        AttendanceSession.status == SessionStatus.COMPLETED
    ).order_by(AttendanceSession.created_at.desc()).all()
    
    result = []
    for sess in sessions:
        subject = db.query(Subject).filter(
            Subject.id == sess.subject_id
        ).first()
        subject_name = subject.subject_name if subject else ("Morning Entry Attendance" if sess.subject_id == "ENTRY" else "Unknown Subject")
        subject_code = subject.subject_code if subject else (sess.subject_id or "")
        
        if sess.subject_id == "ENTRY":
            teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
            present_count = db.query(DayWiseAttendance).join(Student).filter(
                DayWiseAttendance.date == sess.date,
                Student.department_id == teacher.department_id
            ).count() if teacher else 0
        else:
            present_count = db.query(AttendanceMark).filter(AttendanceMark.session_id == sess.id).count()
        
        total_students = 0
        if subject:
            total_students = db.query(Student).filter(
                Student.department_id == subject.department_id,
                Student.semester == subject.semester,
                Student.section == sess.section_id,
                Student.status == "active"
            ).count()
        elif sess.subject_id == "ENTRY":
            teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
            if teacher:
                total_students = db.query(Student).filter(
                    Student.department_id == teacher.department_id,
                    Student.status == "active"
                ).count()
            
        result.append({
            "id": sess.id,
            "date": sess.date.strftime("%Y-%m-%d"),
            "subject": subject_name,
            "code": subject_code,
            "section": sess.section_id or "",
            "time": sess.created_at.strftime("%H:%M") + (f" - {sess.completed_at.strftime('%H:%M')}" if sess.completed_at else ""),
            "present": present_count,
            "total": total_students,
            "status": sess.status.value
        })
        
    return result

class StudentReportResponse(BaseModel):
    roll_number: str
    name: str
    status: str
    time: Optional[str] = None
    method: Optional[str] = None

class SessionReportResponse(BaseModel):
    id: str
    date: str
    subject: str
    code: str
    section: str
    period: str
    students: List[StudentReportResponse]

@router.get("/sessions/{session_id}/report", response_model=SessionReportResponse)
def get_session_report(
    session_id: str,
    token: str = Depends(verify_teacher_session),
    db: Session = Depends(get_db)
):
    session = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    subject = db.query(Subject).filter(
        Subject.id == session.subject_id
    ).first()
    subject_name = subject.subject_name if subject else ("Morning Entry Attendance" if session.subject_id == "ENTRY" else "Unknown Subject")
    subject_code = subject.subject_code if subject else (session.subject_id or "")
    
    roster_students = []
    if subject:
        roster_students = db.query(Student).filter(
            Student.department_id == subject.department_id,
            Student.semester == subject.semester,
            Student.section == session.section_id,
            Student.status == "active"
        ).order_by(Student.roll_no).all()
    elif session.subject_id == "ENTRY":
        teacher = db.query(Teacher).filter(Teacher.id == session.teacher_id).first()
        if teacher:
            roster_students = db.query(Student).filter(
                Student.department_id == teacher.department_id,
                Student.status == "active"
            ).order_by(Student.roll_no).all()
        
    if session.subject_id == "ENTRY":
        day_marks = db.query(DayWiseAttendance, Student).join(Student).filter(
            DayWiseAttendance.date == session.date
        ).all()
        marks_map = {student.roll_no: mark for mark, student in day_marks}
    else:
        marks = db.query(AttendanceMark).filter(AttendanceMark.session_id == session_id).all()
        marks_map = {m.roll_number: m for m in marks}
    
    students_report = []
    for st in roster_students:
        mark = marks_map.get(st.roll_no)
        students_report.append(StudentReportResponse(
            roll_number=st.roll_no,
            name=st.name,
            status="Present" if mark else "Absent",
            time=mark.marked_at.strftime("%I:%M %p") if mark and mark.marked_at else None,
            method=mark.method.value if mark and mark.method else None
        ))
        
    return SessionReportResponse(
        id=session.id,
        date=session.date.strftime("%Y-%m-%d"),
        subject=subject_name,
        code=subject_code,
        section=session.section_id or "",
        period=session.period_id or "",
        students=students_report
    )


