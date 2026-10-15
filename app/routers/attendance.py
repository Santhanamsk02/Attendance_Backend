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
def verify_teacher_session(
    teacher_verification_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> str:
    raw = None
    if teacher_verification_token and "veri-token-" in teacher_verification_token:
        raw = teacher_verification_token.split("veri-token-")[-1].strip()
    elif teacher_verification_token and teacher_verification_token.strip():
        raw = teacher_verification_token.strip()
    elif authorization and "Bearer " in authorization:
        raw_auth = authorization.replace("Bearer ", "").strip()
        if "mock-jwt-teacher-" in raw_auth:
            raw = raw_auth.split("mock-jwt-teacher-")[-1].strip()
        else:
            raw = raw_auth

    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid Teacher Verification Token or Authorization is required to access Attendance systems."
        )

    from sqlalchemy import or_
    teacher = db.query(Teacher).filter(
        or_(
            Teacher.id == raw,
            Teacher.employee_id == raw,
            func.lower(Teacher.email) == raw.lower()
        )
    ).first()
    if teacher:
        return teacher.id
    return raw

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
    
    # Clean section name (e.g. "IV-B" -> "B", "Section B" -> "B")
    raw_sec = request.section_name.strip()
    clean_sec = raw_sec
    if "-" in clean_sec:
        clean_sec = clean_sec.split("-")[-1].strip()
    elif clean_sec.upper().startswith("SECTION"):
        clean_sec = clean_sec.upper().replace("SECTION", "").strip()

    from app.models.timetable import TeacherAssignment
    day_mapping = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}
    dow = day_mapping[request.date.weekday()]
    
    assignment = db.query(TeacherAssignment).filter(
        TeacherAssignment.teacher_id == teacher_id,
        (TeacherAssignment.section_id == raw_sec) | (TeacherAssignment.section_id == clean_sec),
        func.lower(TeacherAssignment.period_id) == request.period_id.strip().lower(),
        TeacherAssignment.day_of_week == dow
    ).first()

    dept_id = assignment.department_id if assignment else (subj.department_id if subj else None)
    
    if not dept_id and request.subject_code == "ENTRY":
        teacher_obj = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if teacher_obj:
            dept_id = teacher_obj.department_id

    # Special check for Morning Entry to avoid duplicate sessions across departments
    if request.subject_code == "ENTRY":
        existing_entry = db.query(AttendanceSession).filter(
            AttendanceSession.date == request.date,
            func.lower(AttendanceSession.period_id) == "morning-entry"
        ).first()
        if existing_entry:
            marks = db.query(AttendanceMark).filter(AttendanceMark.session_id == existing_entry.id).all()
            setattr(existing_entry, 'marked_rolls', [m.roll_number for m in marks])
            setattr(existing_entry, 'subject_code', "ENTRY")
            setattr(existing_entry, 'section_name', existing_entry.section_id or "ALL")
            return existing_entry

    # Existing session lookup: match date, period, section and subject
    # Matches case-insensitively and handles section variations (e.g. 'A' vs 'IV-A')
    existing_session = db.query(AttendanceSession).filter(
        AttendanceSession.date == request.date,
        func.lower(AttendanceSession.period_id) == request.period_id.strip().lower(),
        (AttendanceSession.section_id == raw_sec) | 
        (AttendanceSession.section_id == clean_sec) |
        (AttendanceSession.section_id.ilike(f"%{clean_sec}%")),
        (AttendanceSession.subject_id == subject_id) | 
        (AttendanceSession.subject_id == request.subject_code) |
        (AttendanceSession.subject_id == code)
    ).first()

    if existing_session:
        # Update missing department_id if now known
        if not existing_session.department_id and dept_id:
            existing_session.department_id = dept_id
            db.commit()

        marks = db.query(AttendanceMark).filter(AttendanceMark.session_id == existing_session.id).all()
        setattr(existing_session, 'marked_rolls', [m.roll_number for m in marks])
        setattr(existing_session, 'subject_code', code)
        setattr(existing_session, 'section_name', existing_session.section_id or raw_sec)
        return existing_session


    batch_id = assignment.batch_id if assignment else None
    ay_id = assignment.academic_year_id if assignment else None
    sem = assignment.semester if assignment else (subj.semester if subj else None)
    
    saved_sec = clean_sec if (clean_sec and len(clean_sec) <= 3) else raw_sec

    new_session = AttendanceSession(
        teacher_id=teacher_id,
        subject_id=subject_id,
        section_id=saved_sec,
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
    setattr(new_session, 'section_name', new_session.section_id or raw_sec)
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
            method=ScanMethod.MANUAL_ENTRY,
            marked_at=datetime.now()
        )
        db.add(new_mark)
        
        if is_morning_entry:
            existing_day = db.query(DayWiseAttendance).filter(
                DayWiseAttendance.student_id == student.id,
                DayWiseAttendance.date == db_session.date
            ).first()
            if not existing_day:
                new_day_mark = DayWiseAttendance(
                    student_id=student.id,
                    date=db_session.date,
                    method=ScanMethod.MANUAL_ENTRY,
                    marked_by=token,
                    marked_at=datetime.now()
                )
                db.add(new_day_mark)
            
        added_count += 1

    db_session.status = SessionStatus.COMPLETED
    db_session.completed_at = datetime.now()
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
    is_special_training: bool = False

@router.get("/sessions/history", response_model=List[SessionHistoryResponse])
def get_attendance_history(
    token: str = Depends(verify_teacher_session),
    db: Session = Depends(get_db)
):
    teacher_id = token
    # 1. Regular class sessions
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
            "status": sess.status.value,
            "is_special_training": False
        })
        
    # 2. Special Training sessions - entire attendance taken by all teachers is visible to all faculty
    from app.models.special_training import (
        SpecialTraining,
        SpecialTrainingSession,
        SpecialTrainingMark,
        SpecialTrainingStaffAssignment,
        SpecialTrainingEnrollment,
        SpecialTrainingTimetable
    )
    
    training_sessions = db.query(SpecialTrainingSession).filter(
        SpecialTrainingSession.status == "COMPLETED"
    ).order_by(SpecialTrainingSession.date.desc(), SpecialTrainingSession.created_at.desc()).all()
    
    for tr_sess in training_sessions:
        tr = tr_sess.training
        total_enrolled = db.query(SpecialTrainingEnrollment).filter(
            SpecialTrainingEnrollment.training_id == tr_sess.training_id
        ).count()
        present_count = db.query(SpecialTrainingMark).filter(
            SpecialTrainingMark.session_id == tr_sess.id,
            SpecialTrainingMark.status == "PRESENT"
        ).count()
        
        clean_p = tr_sess.period_id.strip().upper().replace("TR-", "")
        tt_slot = db.query(SpecialTrainingTimetable).filter(
            SpecialTrainingTimetable.training_id == tr_sess.training_id,
            (func.upper(SpecialTrainingTimetable.period_id) == clean_p) |
            (func.upper(SpecialTrainingTimetable.period_id) == tr_sess.period_id.strip().upper())
        ).first()
        time_str = f"{tt_slot.start_time} - {tt_slot.end_time}" if (tt_slot and tt_slot.start_time and tt_slot.end_time) else (
            tr_sess.created_at.strftime("%H:%M") + (f" - {tr_sess.completed_at.strftime('%H:%M')}" if tr_sess.completed_at else "")
        )
        
        result.append({
            "id": tr_sess.id,
            "date": tr_sess.date.strftime("%Y-%m-%d"),
            "subject": tr.name if tr else "Special Training",
            "code": f"TR-{clean_p}",
            "section": (tr.batch_name if tr else "TRAINING") or "TRAINING",
            "time": time_str,
            "present": present_count,
            "total": total_enrolled,
            "status": tr_sess.status,
            "is_special_training": True
        })
        
    result.sort(key=lambda x: x["date"], reverse=True)
    return result

class StudentReportResponse(BaseModel):
    roll_number: str
    name: str
    status: str
    time: Optional[str] = None
    method: Optional[str] = None
    marked_by: Optional[str] = None
    department: Optional[str] = None
    section: Optional[str] = None

class SessionReportResponse(BaseModel):
    id: str
    date: str
    subject: str
    code: str
    section: str
    period: str
    students: List[StudentReportResponse]
    marked_teachers: List[str] = []
    is_special_training: bool = False

@router.get("/sessions/{session_id}/report", response_model=SessionReportResponse)
def get_session_report(
    session_id: str,
    token: str = Depends(verify_teacher_session),
    db: Session = Depends(get_db)
):
    session = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session:
        # Check Special Training Session
        from app.models.special_training import (
            SpecialTraining,
            SpecialTrainingSession,
            SpecialTrainingMark,
            SpecialTrainingEnrollment
        )
        from app.models.department import Department
        tr_sess = db.query(SpecialTrainingSession).filter(SpecialTrainingSession.id == session_id).first()
        if tr_sess:
            tr = tr_sess.training
            enrolled = db.query(
                Student.id,
                Student.roll_no,
                Student.name,
                Student.department_id,
                Department.name.label("department_name"),
                Student.section
            ).join(
                SpecialTrainingEnrollment, SpecialTrainingEnrollment.student_id == Student.id
            ).outerjoin(
                Department, Department.id == Student.department_id
            ).filter(
                SpecialTrainingEnrollment.training_id == tr_sess.training_id
            ).order_by(Student.roll_no).all()
            
            marks = db.query(SpecialTrainingMark).filter(SpecialTrainingMark.session_id == session_id).all()
            marks_map = {m.student_id: m for m in marks}
            
            # Find all contributing faculty who marked students present in this session
            contrib_ids = {m.marked_by_teacher_id for m in marks if m.marked_by_teacher_id and m.status == "PRESENT"}
            from sqlalchemy import or_
            marked_teachers = [t[0] for t in db.query(Teacher.name).filter(
                or_(Teacher.id.in_(contrib_ids), Teacher.employee_id.in_(contrib_ids))
            ).all()] if contrib_ids else []

            students_report = []
            for st in enrolled:
                m = marks_map.get(st.id)
                is_pres = (m and m.status == "PRESENT")
                status_str = "Present" if is_pres else "Absent"
                marked_time = m.marked_at.strftime("%I:%M %p") if (m and m.marked_at) else None
                method_str = m.method if m else None
                marked_by_teacher = None
                if is_pres and m:
                    if m.marked_by:
                        marked_by_teacher = m.marked_by.name
                    elif m.marked_by_teacher_id:
                        t = db.query(Teacher).filter(
                            or_(Teacher.id == m.marked_by_teacher_id, Teacher.employee_id == m.marked_by_teacher_id)
                        ).first()
                        if t:
                            marked_by_teacher = t.name

                students_report.append(StudentReportResponse(
                    roll_number=st.roll_no,
                    name=st.name,
                    status=status_str,
                    time=marked_time,
                    method=method_str,
                    marked_by=marked_by_teacher,
                    department=st.department_name or "N/A",
                    section=st.section or "N/A"
                ))
                
            clean_p = tr_sess.period_id.strip().upper().replace("TR-", "")
            return SessionReportResponse(
                id=tr_sess.id,
                date=tr_sess.date.strftime("%Y-%m-%d"),
                subject=tr.name if tr else "Special Training",
                code=f"TR-{clean_p}",
                section=(tr.batch_name if tr else "TRAINING") or "TRAINING",
                period=clean_p,
                students=students_report,
                marked_teachers=marked_teachers,
                is_special_training=True
            )
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
    
    teacher_name = session.teacher.name if session.teacher else None
    marked_teachers = [teacher_name] if teacher_name else []

    students_report = []
    for st in roster_students:
        mark = marks_map.get(st.roll_no)
        students_report.append(StudentReportResponse(
            roll_number=st.roll_no,
            name=st.name,
            status="Present" if mark else "Absent",
            time=mark.marked_at.strftime("%I:%M %p") if mark and mark.marked_at else None,
            method=mark.method.value if mark and mark.method else None,
            marked_by=teacher_name if mark else None,
            department=st.department_rel.name if getattr(st, 'department_rel', None) else None,
            section=st.section
        ))
        
    return SessionReportResponse(
        id=session.id,
        date=session.date.strftime("%Y-%m-%d"),
        subject=subject_name,
        code=subject_code,
        section=session.section_id or "",
        period=session.period_id or "",
        students=students_report,
        marked_teachers=marked_teachers,
        is_special_training=False
    )



