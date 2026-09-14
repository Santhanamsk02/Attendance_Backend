from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from typing import List, Optional
from datetime import datetime, date

from app.database.database import get_db
from app.models.attendance import AttendanceSession, SessionStatus, AttendanceMark
from app.models.student import Student, StudentEnrollment
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.reference import AcademicYear

router = APIRouter(prefix="/admin/attendance", tags=["Admin Attendance Analytics"])

def verify_admin(role: str = Depends(lambda: "admin")):
    pass

@router.get("/students")
def search_student_attendance(
    query: Optional[str] = None,
    departmentId: Optional[str] = None,
    batchId: Optional[str] = None,
    section: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db)
):
    q = db.query(Student, StudentEnrollment, AcademicYear).join(
        StudentEnrollment, Student.id == StudentEnrollment.student_id
    ).outerjoin(
        AcademicYear, StudentEnrollment.academic_year_id == AcademicYear.id
    ).filter(Student.status == "active")
    
    if departmentId:
        q = q.filter(StudentEnrollment.department_id == departmentId)
    if batchId:
        q = q.filter(StudentEnrollment.batch_id == batchId)
    if section:
        q = q.filter(StudentEnrollment.section_id == section)
        
    if query:
        q = q.filter(or_(
            Student.roll_no.ilike(f"%{query}%"),
            Student.name.ilike(f"%{query}%")
        ))
        
    total = q.count()
    records = q.order_by(Student.roll_no).offset((page - 1) * page_size).limit(page_size).all()
    
    res = []
    
    # Pre-fetch all sessions mapping
    for student, enroll, ac_year in records:
        # Expected sessions matching enrollment
        expected_sessions = db.query(AttendanceSession).filter(
            AttendanceSession.status == SessionStatus.COMPLETED,
            AttendanceSession.department_id == enroll.department_id,
            AttendanceSession.academic_year_id == enroll.academic_year_id,
            AttendanceSession.semester == enroll.semester,
            AttendanceSession.section_id == enroll.section_id
        ).count()
        
        present_count = db.query(AttendanceMark).join(AttendanceSession).filter(
            AttendanceMark.student_id == student.id,
            AttendanceMark.status == "PRESENT",
            AttendanceSession.academic_year_id == enroll.academic_year_id,
            AttendanceSession.semester == enroll.semester
        ).count()
        
        attendance_percentage = 0
        if expected_sessions > 0:
            attendance_percentage = round((present_count / expected_sessions) * 100, 2)
            
        res.append({
            "id": student.id,
            "roll_no": student.roll_no,
            "name": student.name,
            "department": enroll.department_id,
            "department_name": student.department_rel.name if student.department_rel else "Unknown",
            "department_code": student.department_rel.code if student.department_rel else "Unknown",
            "batch": enroll.batch_id,
            "batch_name": student.batch_rel.batch_name if student.batch_rel else "Unknown",
            "current_year": student.batch_rel.current_year if student.batch_rel else None,
            "semester": enroll.semester,
            "section": enroll.section_id,
            "academic_year": ac_year.name if ac_year else str(enroll.academic_year_id),
            "expected_sessions": expected_sessions,
            "present_sessions": present_count,
            "attendance_percentage": attendance_percentage
        })
        
    # Sort out duplicates if any student was enrolled multiple times but paginated (simplification)
    return {
        "items": res,
        "total": total,
        "page": page,
        "size": page_size
    }


@router.get("/students/{student_id}/report")
def get_student_attendance_profile(
    student_id: str,
    db: Session = Depends(get_db)
):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
        
    enrolls = db.query(StudentEnrollment).filter(StudentEnrollment.student_id == student_id).all()
    
    # Collect all historical expected sessions for this student's enrollments
    sessions = []
    
    for enroll in enrolls:
        # Find expected sessions for this enrollment block
        enroll_sessions = db.query(AttendanceSession, Subject).join(Subject).filter(
            AttendanceSession.status == SessionStatus.COMPLETED,
            AttendanceSession.department_id == enroll.department_id,
            AttendanceSession.academic_year_id == enroll.academic_year_id,
            AttendanceSession.semester == enroll.semester,
            AttendanceSession.section_id == enroll.section_id
        ).all()
        sessions.extend(enroll_sessions)
        
    sessions.sort(key=lambda x: (x[0].date, x[0].period_id), reverse=True)
    
    marks = db.query(AttendanceMark).filter(
        AttendanceMark.student_id == student.id,
        AttendanceMark.status == "PRESENT"
    ).all()
    marked_session_ids = {m.session_id for m in marks}
    
    history = []
    for sess, sub in sessions:
        is_present = sess.id in marked_session_ids
        history.append({
            "session_id": sess.id,
            "date": sess.date.strftime("%Y-%m-%d"),
            "period": sess.period_id,
            "subject_code": sub.subject_code,
            "subject_name": sub.subject_name,
            "teacher_id": sess.teacher_id,
            "status": "Present" if is_present else "Absent"
        })
        
    expected_classes = len(sessions)
    present_classes = len(marked_session_ids)
    absent_classes = expected_classes - present_classes
    overall = round((present_classes / expected_classes * 100), 2) if expected_classes > 0 else 0
        
    current_enroll = enrolls[-1] if enrolls else None
    
    return {
        "student": {
            "id": student.id,
            "roll_no": student.roll_no,
            "name": student.name,
            "department": current_enroll.department_id if current_enroll else None,
            "batch": current_enroll.batch_id if current_enroll else None,
            "semester": current_enroll.semester if current_enroll else None,
            "section": current_enroll.section_id if current_enroll else None,
            "overall_attendance": overall,
            "expected_classes": expected_classes,
            "present_classes": present_classes,
            "absent_classes": absent_classes
        },
        "history": history
    }

@router.get("/history/session/{session_id}")
def get_session_history_details(
    session_id: str,
    db: Session = Depends(get_db)
):
    session = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    subject = db.query(Subject).filter(Subject.id == session.subject_id).first()
    teacher = db.query(Teacher).filter(Teacher.id == session.teacher_id).first()
    
    # Students expected
    expected_students = db.query(Student).join(
        StudentEnrollment, Student.id == StudentEnrollment.student_id
    ).filter(
        StudentEnrollment.department_id == session.department_id,
        StudentEnrollment.academic_year_id == session.academic_year_id,
        StudentEnrollment.semester == session.semester,
        StudentEnrollment.section_id == session.section_id,
        Student.status == "active"
    ).order_by(Student.roll_no).all()
    
    # Marks
    marks = db.query(AttendanceMark).filter(AttendanceMark.session_id == session_id).all()
    marks_map = {m.student_id: m for m in marks}
    
    marks_data = []
    present_count = 0
    for st in expected_students:
        mark = marks_map.get(st.id)
        if mark and mark.status == "PRESENT":
            present_count += 1
            status = "PRESENT"
        else:
            status = "ABSENT"
            
        marks_data.append({
            "student_id": st.id,
            "student_name": st.name,
            "roll_no": st.roll_no,
            "status": status,
            "method": mark.method.value if mark and mark.method else None,
            "marked_at": mark.marked_at.strftime("%I:%M %p") if mark and mark.marked_at else None
        })
        
    return {
        "session": {
            "subjectName": subject.subject_name if subject else "Unknown",
            "teacherName": teacher.name if teacher else "Unknown",
            "date": session.date.strftime("%Y-%m-%d"),
            "period": session.period_id
        },
        "summary": {
            "total": len(expected_students),
            "present": present_count,
            "absent": len(expected_students) - present_count
        },
        "marks": marks_data
    }
