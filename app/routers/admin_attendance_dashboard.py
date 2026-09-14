from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case
from typing import List, Optional
from datetime import datetime
from collections import defaultdict

from app.database.database import get_db
from app.models.attendance import AttendanceSession, SessionStatus, AttendanceMark
from app.models.student import Student, StudentEnrollment
from app.models.subject import Subject
from app.models.batch import Batch
from app.models.teacher import Teacher

router = APIRouter(prefix="/admin/attendance/dashboard", tags=["Admin Attendance Dashboard"])

def apply_filters(q, model, filters: dict):
    if filters.get("department_id") and hasattr(model, 'department_id'):
        q = q.filter(model.department_id == filters["department_id"])
    if filters.get("batch_id") and hasattr(model, 'batch_id'):
        q = q.filter(model.batch_id == filters["batch_id"])
    if filters.get("semester") and hasattr(model, 'semester'):
        q = q.filter(model.semester == filters["semester"])
    if filters.get("section") and hasattr(model, 'section_id'):
        q = q.filter(model.section_id == filters["section"])
    if filters.get("subject_code") and hasattr(model, 'subject_code'):
        q = q.filter(model.subject_code == filters["subject_code"])
    return q

@router.get("/overview")
def get_dashboard_overview(
    department_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    semester: Optional[int] = None,
    section: Optional[str] = None,
    subject_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        filters = {
            "department_id": department_id,
            "batch_id": batch_id,
            "semester": semester,
            "section": section,
        }
        
        # 1. Total Enrolled Students Historically against filters
        student_q = db.query(StudentEnrollment.student_id).distinct()
        student_q = apply_filters(student_q, StudentEnrollment, filters)
        total_students = student_q.count()
        
        # 3. Get applicable sessions directly from AttendanceSession Context!
        sess_q = db.query(AttendanceSession).filter(AttendanceSession.status == SessionStatus.COMPLETED)
        if subject_code:
            sess_q = sess_q.join(Subject, AttendanceSession.subject_id == Subject.id)
            sess_q = sess_q.filter(Subject.subject_code == subject_code)
        
        # filter sessions based on filters
        sess_q = apply_filters(sess_q, AttendanceSession, filters)
            
        if start_date:
            sess_q = sess_q.filter(AttendanceSession.date >= start_date)
        if end_date:
            sess_q = sess_q.filter(AttendanceSession.date <= end_date)
            
        completed_sessions = sess_q.all()
        total_sessions = len(completed_sessions)
        
        expected_marks = 0
        present_marks = 0
        session_ids = [s.id for s in completed_sessions]
        
        if session_ids:
            # We look up Expected Counts from StudentEnrollments historically
            agg_students = db.query(
                StudentEnrollment.department_id, 
                StudentEnrollment.academic_year_id,
                StudentEnrollment.semester, 
                StudentEnrollment.section_id, 
                func.count(StudentEnrollment.student_id)
            )
            agg_students = apply_filters(agg_students, StudentEnrollment, filters)
            student_counts = agg_students.group_by(
                StudentEnrollment.department_id, 
                StudentEnrollment.academic_year_id,
                StudentEnrollment.semester, 
                StudentEnrollment.section_id
            ).all()
            
            # map: (dept, ay, sem, sec) -> expected_count
            std_map = {(r[0], r[1], r[2], r[3]): r[4] for r in student_counts}
            
            trend_data = defaultdict(lambda: {"expected": 0, "present": 0, "sessions": 0})
            
            # Query actual present marks by session
            present_grouped = db.query(AttendanceMark.session_id, func.count(AttendanceMark.id)).filter(
                AttendanceMark.session_id.in_(session_ids),
                AttendanceMark.status == "PRESENT"
            ).group_by(AttendanceMark.session_id).all()
            
            present_mark_map = {r[0]: r[1] for r in present_grouped}

            for sess in completed_sessions:
                count = std_map.get((sess.department_id, sess.academic_year_id, sess.semester, sess.section_id), 0)
                expected_marks += count
                p_count = present_mark_map.get(sess.id, 0)
                present_marks += p_count
                
                # Trend aggregation by date
                d_str = sess.date.strftime("%Y-%m-%d")
                trend_data[d_str]["expected"] += count
                trend_data[d_str]["present"] += p_count
                trend_data[d_str]["sessions"] += 1
                
            absent_marks = max(0, expected_marks - present_marks)
            overall_percentage = round((present_marks / expected_marks * 100), 1) if expected_marks > 0 else 0
            
            formatted_trend = []
            for d in sorted(trend_data.keys()):
                d_exp = trend_data[d]["expected"]
                d_pre = trend_data[d]["present"]
                formatted_trend.append({
                    "date": d,
                    "sessions": trend_data[d]["sessions"],
                    "present": d_pre,
                    "absent": max(0, d_exp - d_pre),
                    "attendancePct": round((d_pre / d_exp * 100), 1) if d_exp > 0 else 0
                })
        else:
            absent_marks = 0
            overall_percentage = 0
            formatted_trend = []

        year_wise = [{"year": f"{y} Year", "present": 0, "expected": 0, "students": 0, "sessions": 0} for y in ["1st", "2nd", "3rd", "4th"]]
        semester_wise = [{"semester": i, "present": 0, "expected": 0, "students": 0, "sessions": 0, "subjects": set()} for i in range(1, 9)]
        
        if session_ids:
            # Map student sums dynamically
            for (dept, ay, sem, sec), count in std_map.items():
                if sem and 1 <= sem <= 8:
                    semester_wise[sem-1]["students"] += count
                    y_idx = (sem-1)//2
                    year_wise[y_idx]["students"] += count
                    
            # Join Subject explicitly just for subject_code aggregation to avoid extra DB pings
            subj_dict = {s.id: s.subject_code for s in db.query(Subject.id, Subject.subject_code).all()}
            
            for sess in completed_sessions:
                s_sem = sess.semester
                if not s_sem or s_sem < 1 or s_sem > 8: continue
                
                s_count = std_map.get((sess.department_id, sess.academic_year_id, sess.semester, sess.section_id), 0)
                p_count = present_mark_map.get(sess.id, 0)
                code = subj_dict.get(sess.subject_id, "UNK")
                
                sem_idx = s_sem - 1
                y_idx = sem_idx // 2
                
                semester_wise[sem_idx]["sessions"] += 1
                semester_wise[sem_idx]["expected"] += s_count
                semester_wise[sem_idx]["present"] += p_count
                semester_wise[sem_idx]["subjects"].add(code)
                
                year_wise[y_idx]["sessions"] += 1
                year_wise[y_idx]["expected"] += s_count
                year_wise[y_idx]["present"] += p_count

        for yw in year_wise:
            yw["attendancePct"] = round(yw["present"] / yw["expected"] * 100, 1) if yw["expected"] > 0 else 0
            yw["absent"] = max(0, yw["expected"] - yw["present"])

        for sw in semester_wise:
            sw["attendancePct"] = round(sw["present"] / sw["expected"] * 100, 1) if sw["expected"] > 0 else 0
            sw["absent"] = max(0, sw["expected"] - sw["present"])
            sw["subjectsCount"] = len(sw["subjects"])
            del sw["subjects"]

        return {
            "kpis": {
                "totalStudents": total_students,
                "overallAttendance": overall_percentage,
                "present": present_marks,
                "absent": absent_marks,
                "sessions": total_sessions
            },
            "trend": formatted_trend,
            "distribution": [
                {"name": "Present", "value": present_marks},
                {"name": "Absent", "value": absent_marks}
            ],
            "yearWise": year_wise,
            "semesterWise": semester_wise
        }
    except Exception as e:
        print(f"Error in overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
def get_dashboard_sessions(
    department_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    section: Optional[str] = None,
    subject_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    try:
        query = db.query(AttendanceSession, Teacher, Subject).join(
            Teacher, AttendanceSession.teacher_id == Teacher.id
        ).join(
            Subject, AttendanceSession.subject_id == Subject.id
        )
        
        filters = {
            "department_id": department_id,
            "batch_id": batch_id,
            "section": section,
        }
        query = apply_filters(query, AttendanceSession, filters)
        
        if subject_code:
            query = query.filter(Subject.subject_code == subject_code)
        if start_date:
            query = query.filter(AttendanceSession.date >= start_date)
        if end_date:
            query = query.filter(AttendanceSession.date <= end_date)
        if status:
            query = query.filter(AttendanceSession.status == SessionStatus[status.upper()])
            
        total = query.count()
        results = query.order_by(AttendanceSession.date.desc(), AttendanceSession.period_id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        
        formatted_results = []
        for sess, teacher, subject in results:
            expected = db.query(StudentEnrollment).filter(
                StudentEnrollment.department_id == sess.department_id,
                StudentEnrollment.academic_year_id == sess.academic_year_id,
                StudentEnrollment.semester == sess.semester,
                StudentEnrollment.section_id == sess.section_id
            ).count()
            
            present = db.query(AttendanceMark).filter(
                AttendanceMark.session_id == sess.id,
                AttendanceMark.status == "PRESENT"
            ).count()
            
            formatted_results.append({
                "id": sess.id,
                "date": sess.date.strftime("%Y-%m-%d"),
                "period": sess.period_id,
                "subjectCode": subject.subject_code,
                "subjectName": subject.subject_name,
                "departmentId": sess.department_id,
                "section": sess.section_id,
                "teacherName": teacher.name,
                "status": sess.status.value,
                "students": expected,
                "present": present,
                "absent": max(0, expected - present),
                "attendancePct": round(present / expected * 100, 1) if expected > 0 else 0
            })
            
        return {
            "items": formatted_results,
            "total": total,
            "page": page,
            "pageSize": page_size
        }
    except Exception as e:
        print(f"Error in sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts")
def get_low_attendance_alerts(
    threshold: float = 75.0,
    department_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    semester: Optional[int] = None,
    section: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    try:
        filters = {
            "department_id": department_id,
            "batch_id": batch_id,
            "semester": semester,
            "section": section,
        }
        
        enrolls_q = db.query(StudentEnrollment, Student).join(Student, StudentEnrollment.student_id == Student.id)
        enrolls_q = apply_filters(enrolls_q, StudentEnrollment, filters)
        records = enrolls_q.all()
        
        if not records:
            return {"items": [], "total": 0, "page": page, "pageSize": page_size}
            
        sessions = db.query(AttendanceSession.id, AttendanceSession.department_id, AttendanceSession.academic_year_id, AttendanceSession.semester, AttendanceSession.section_id).filter(
            AttendanceSession.status == SessionStatus.COMPLETED
        ).all()
        
        expected_sessions = defaultdict(list)
        for sess in sessions:
            expected_sessions[(sess.department_id, sess.academic_year_id, sess.semester, sess.section_id)].append(sess.id)
            
        all_session_ids = [s.id for s in sessions]
        student_ids = [r[1].id for r in records]
        
        mark_q = db.query(AttendanceMark.student_id, AttendanceMark.session_id).filter(
            AttendanceMark.session_id.in_(all_session_ids),
            AttendanceMark.student_id.in_(student_ids),
            AttendanceMark.status == "PRESENT"
        ).all()
        
        student_marks = defaultdict(set)
        for m in mark_q:
            student_marks[m.student_id].add(m.session_id)
            
        alerts = []
        seen = set()
        for enroll, student in records:
            if student.id in seen: continue # Skip if processed earlier enrollments (simplified for alerts)
            seen.add(student.id)
            
            expected_ids = expected_sessions.get((enroll.department_id, enroll.academic_year_id, enroll.semester, enroll.section_id), [])
            exp_count = len(expected_ids)
            if exp_count > 0:
                attended = student_marks.get(student.id, set())
                pre_count = len(attended.intersection(expected_ids))
                pct = round((pre_count / exp_count) * 100, 1)
                
                if pct < threshold:
                    risk_level = "High" if pct < 50 else ("Medium" if pct < 65 else "Low")
                    alerts.append({
                        "id": student.id,
                        "rollNo": student.roll_no,
                        "name": student.name,
                        "departmentId": enroll.department_id,
                        "year": (enroll.semester - 1) // 2 + 1 if enroll.semester else 1,
                        "semester": enroll.semester,
                        "section": enroll.section_id,
                        "attendancePct": pct,
                        "present": pre_count,
                        "absent": exp_count - pre_count,
                        "riskLevel": risk_level
                    })
                    
        alerts.sort(key=lambda x: x["attendancePct"])
        total = len(alerts)
        paginated_alerts = alerts[(page - 1) * page_size : page * page_size]
        
        return {
            "items": paginated_alerts,
            "total": total,
            "page": page,
            "pageSize": page_size
        }
    except Exception as e:
        print(f"Error in alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/subjects")
def get_dashboard_subjects(
    department_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    semester: Optional[int] = None,
    db: Session = Depends(get_db)
):
    try:
        filters = {}
        if department_id: filters["department_id"] = department_id
        if batch_id: filters["batch_id"] = batch_id
        if semester: filters["semester"] = semester
        
        subj_q = apply_filters(db.query(Subject), Subject, filters)
        subjects = subj_q.all()
        
        if not subjects: return []
            
        subject_map = {s.id: s for s in subjects}
        subj_ids = list(subject_map.keys())
        
        sessions = db.query(AttendanceSession.id, AttendanceSession.subject_id, AttendanceSession.department_id, AttendanceSession.academic_year_id, AttendanceSession.semester, AttendanceSession.section_id).filter(
            AttendanceSession.status == SessionStatus.COMPLETED,
            AttendanceSession.subject_id.in_(subj_ids)
        ).all()
        
        agg_students = db.query(
            StudentEnrollment.department_id, StudentEnrollment.academic_year_id, StudentEnrollment.semester, StudentEnrollment.section_id, func.count(StudentEnrollment.student_id)
        )
        agg_students = apply_filters(agg_students, StudentEnrollment, filters).group_by(StudentEnrollment.department_id, StudentEnrollment.academic_year_id, StudentEnrollment.semester, StudentEnrollment.section_id).all()
        std_map = {(r[0], r[1], r[2], r[3]): r[4] for r in agg_students}
        
        sess_present = db.query(AttendanceMark.session_id, func.count(AttendanceMark.id)).filter(
            AttendanceMark.session_id.in_([s.id for s in sessions]),
            AttendanceMark.status == "PRESENT"
        ).group_by(AttendanceMark.session_id).all()
        present_map = {r[0]: r[1] for r in sess_present}
        
        res_map = defaultdict(lambda: {"expected": 0, "present": 0, "sessionsCount": 0})
        
        for sess in sessions:
            sub = subject_map[sess.subject_id]
            s_count = std_map.get((sess.department_id, sess.academic_year_id, sess.semester, sess.section_id), 0)
            p_count = present_map.get(sess.id, 0)
            
            rm = res_map[sub.id]
            rm["expected"] += s_count
            rm["present"] += p_count
            rm["sessionsCount"] += 1
            
        results = []
        for sid, sub in subject_map.items():
            rm = res_map[sid]
            if rm["sessionsCount"] > 0:
                results.append({
                    "subjectCode": sub.subject_code,
                    "subjectName": sub.subject_name,
                    "sessions": rm["sessionsCount"],
                    "present": rm["present"],
                    "absent": max(0, rm["expected"] - rm["present"]),
                    "attendancePct": round((rm["present"] / rm["expected"]) * 100, 1) if rm["expected"] > 0 else 0
                })
                
        results.sort(key=lambda x: x["attendancePct"])
        return results
    except Exception as e:
        print(f"Error in subjects: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/report/detailed")
def get_detailed_report(
    department_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    semester: Optional[int] = None,
    section: Optional[str] = None,
    subject_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        # Complex join across Student, Marks, Session, Subject, Teacher
        query = db.query(
            AttendanceMark, AttendanceSession, Student, Teacher, Subject
        ).select_from(AttendanceMark).join(
            AttendanceSession, AttendanceMark.session_id == AttendanceSession.id
        ).join(
            Student, AttendanceMark.student_id == Student.id
        ).join(
            Teacher, AttendanceSession.teacher_id == Teacher.id
        ).join(
            Subject, AttendanceSession.subject_id == Subject.id
        ).filter(AttendanceSession.status == SessionStatus.COMPLETED)
        
        # We apply filtering using the session context (historical context) for safety
        if department_id: query = query.filter(AttendanceSession.department_id == department_id)
        if batch_id: query = query.filter(AttendanceSession.batch_id == batch_id)
        if semester: query = query.filter(AttendanceSession.semester == semester)
        if section: query = query.filter(AttendanceSession.section_id == section)
        
        if subject_code: query = query.filter(Subject.subject_code == subject_code)
        if start_date: query = query.filter(AttendanceSession.date >= start_date)
        if end_date: query = query.filter(AttendanceSession.date <= end_date)
        
        # Order by Date descending so newest is on top
        results = query.order_by(AttendanceSession.date.desc(), AttendanceSession.period_id.asc(), Student.roll_no.asc()).all()
        
        formatted = []
        for mark, sess, student, teacher, sub in results:
            formatted.append({
                "date": sess.date.strftime("%Y-%m-%d"),
                "period": sess.period_id,
                "subject": sub.subject_name,
                "subjectCode": sub.subject_code,
                "teacher": teacher.name,
                "department": sess.department_id,
                "semester": sess.semester,
                "section": sess.section_id,
                "rollNumber": student.roll_no,
                "studentName": student.name,
                "status": mark.status.value if mark.status else "PRESENT",
                "method": mark.method.value if mark.method else "",
                "markedAt": mark.marked_at.strftime("%Y-%m-%d %H:%M:%S") if mark.marked_at else "",
                "remarks": mark.remarks or ""
            })
            
        return formatted
    except Exception as e:
        print(f"Error in detailed report: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/departments")
def get_dashboard_departments(
    batch_id: Optional[str] = None,
    semester: Optional[int] = None,
    db: Session = Depends(get_db)
):
    try:
        filters = {}
        if batch_id: filters["batch_id"] = batch_id
        if semester: filters["semester"] = semester
        
        from app.models.department import Department
        depts = db.query(Department).all()
        dept_map = {d.id: d for d in depts}
        
        sessions = db.query(AttendanceSession.id, AttendanceSession.department_id, AttendanceSession.academic_year_id, AttendanceSession.semester, AttendanceSession.section_id).filter(
            AttendanceSession.status == SessionStatus.COMPLETED
        ).all()
        
        agg_students = db.query(
            StudentEnrollment.department_id, StudentEnrollment.academic_year_id, StudentEnrollment.semester, StudentEnrollment.section_id, func.count(StudentEnrollment.student_id)
        )
        agg_students = apply_filters(agg_students, StudentEnrollment, filters).group_by(StudentEnrollment.department_id, StudentEnrollment.academic_year_id, StudentEnrollment.semester, StudentEnrollment.section_id).all()
        std_map = {(r[0], r[1], r[2], r[3]): r[4] for r in agg_students}
        
        sess_present = db.query(AttendanceMark.session_id, func.count(AttendanceMark.id)).filter(
            AttendanceMark.session_id.in_([s.id for s in sessions]),
            AttendanceMark.status == "PRESENT"
        ).group_by(AttendanceMark.session_id).all()
        present_map = {r[0]: r[1] for r in sess_present}
        
        res_map = defaultdict(lambda: {"expected": 0, "present": 0, "sessionsCount": 0})
        
        for sess in sessions:
            if semester and sess.semester != semester: continue
            if not sess.department_id: continue
            
            s_count = std_map.get((sess.department_id, sess.academic_year_id, sess.semester, sess.section_id), 0)
            p_count = present_map.get(sess.id, 0)
            
            rm = res_map[sess.department_id]
            rm["expected"] += s_count
            rm["present"] += p_count
            rm["sessionsCount"] += 1
            
        results = []
        for did, d_obj in dept_map.items():
            rm = res_map[did]
            if rm["sessionsCount"] > 0:
                results.append({
                    "departmentId": did,
                    "departmentName": d_obj.name,
                    "sessions": rm["sessionsCount"],
                    "present": rm["present"],
                    "absent": max(0, rm["expected"] - rm["present"]),
                    "attendancePct": round((rm["present"] / rm["expected"]) * 100, 1) if rm["expected"] > 0 else 0
                })
                
        results.sort(key=lambda x: x["attendancePct"])
        return results
    except Exception as e:
        print(f"Error in departments: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sections")
def get_dashboard_sections(
    department_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    semester: Optional[int] = None,
    db: Session = Depends(get_db)
):
    try:
        filters = {}
        if department_id: filters["department_id"] = department_id
        if batch_id: filters["batch_id"] = batch_id
        if semester: filters["semester"] = semester
        
        sessions = db.query(AttendanceSession.id, AttendanceSession.department_id, AttendanceSession.academic_year_id, AttendanceSession.semester, AttendanceSession.section_id).filter(
            AttendanceSession.status == SessionStatus.COMPLETED
        ).all()
        
        agg_students = db.query(
            StudentEnrollment.department_id, StudentEnrollment.academic_year_id, StudentEnrollment.semester, StudentEnrollment.section_id, func.count(StudentEnrollment.student_id)
        )
        agg_students = apply_filters(agg_students, StudentEnrollment, filters).group_by(StudentEnrollment.department_id, StudentEnrollment.academic_year_id, StudentEnrollment.semester, StudentEnrollment.section_id).all()
        std_map = {(r[0], r[1], r[2], r[3]): r[4] for r in agg_students}
        
        sess_present = db.query(AttendanceMark.session_id, func.count(AttendanceMark.id)).filter(
            AttendanceMark.session_id.in_([s.id for s in sessions]),
            AttendanceMark.status == "PRESENT"
        ).group_by(AttendanceMark.session_id).all()
        present_map = {r[0]: r[1] for r in sess_present}
        
        from app.models.reference import Section
        sec_map = {s.id: s.name for s in db.query(Section).all()}
        
        res_map = defaultdict(lambda: {"expected": 0, "present": 0, "sessionsCount": 0, "name": ""})
        
        for sess in sessions:
            if department_id and sess.department_id != department_id: continue
            # Soft filtering manually out since we didn't apply_filters here directly (to simplify query scope)
            if semester and sess.semester != semester: continue
            if not sess.section_id: continue
            
            s_count = std_map.get((sess.department_id, sess.academic_year_id, sess.semester, sess.section_id), 0)
            p_count = present_map.get(sess.id, 0)
            
            if s_count == 0: continue
            
            rm = res_map[sess.section_id]
            rm["name"] = sec_map.get(sess.section_id, sess.section_id)
            rm["expected"] += s_count
            rm["present"] += p_count
            rm["sessionsCount"] += 1
            
        results = []
        for sid, rm in res_map.items():
            if rm["sessionsCount"] > 0:
                results.append({
                    "sectionId": sid,
                    "sectionName": rm["name"],
                    "sessions": rm["sessionsCount"],
                    "present": rm["present"],
                    "absent": max(0, rm["expected"] - rm["present"]),
                    "attendancePct": round((rm["present"] / rm["expected"]) * 100, 1) if rm["expected"] > 0 else 0
                })
                
        results.sort(key=lambda x: x["attendancePct"])
        return results
    except Exception as e:
        print(f"Error in sections: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/teachers")
def get_dashboard_teachers(
    department_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        teachers = db.query(Teacher).all()
        t_map = {t.id: t for t in teachers}
        
        sessions = db.query(AttendanceSession.id, AttendanceSession.teacher_id, AttendanceSession.subject_id, AttendanceSession.department_id, AttendanceSession.academic_year_id, AttendanceSession.semester, AttendanceSession.section_id).filter(
            AttendanceSession.status == SessionStatus.COMPLETED
        ).all()
        
        agg_students = db.query(
            StudentEnrollment.department_id, StudentEnrollment.academic_year_id, StudentEnrollment.semester, StudentEnrollment.section_id, func.count(StudentEnrollment.student_id)
        ).group_by(StudentEnrollment.department_id, StudentEnrollment.academic_year_id, StudentEnrollment.semester, StudentEnrollment.section_id).all()
        std_map = {(r[0], r[1], r[2], r[3]): r[4] for r in agg_students}
        
        sess_present = db.query(AttendanceMark.session_id, func.count(AttendanceMark.id)).filter(
            AttendanceMark.session_id.in_([s.id for s in sessions]),
            AttendanceMark.status == "PRESENT"
        ).group_by(AttendanceMark.session_id).all()
        present_map = {r[0]: r[1] for r in sess_present}
        
        res_map = defaultdict(lambda: {"expected": 0, "present": 0, "sessionsCount": 0, "subjects": set()})
        
        from app.models.subject import Subject
        sub_dict = {s.id: s.subject_name for s in db.query(Subject).all()}
        
        for sess in sessions:
            if department_id and sess.department_id != department_id: continue
            
            s_count = std_map.get((sess.department_id, sess.academic_year_id, sess.semester, sess.section_id), 0)
            p_count = present_map.get(sess.id, 0)
            
            rm = res_map[sess.teacher_id]
            rm["subjects"].add(sub_dict.get(sess.subject_id, "Unknown"))
            rm["expected"] += s_count
            rm["present"] += p_count
            rm["sessionsCount"] += 1
            
        results = []
        for tid, t_obj in t_map.items():
            rm = res_map.get(tid)
            if rm and rm["sessionsCount"] > 0:
                results.append({
                    "teacherId": tid,
                    "teacherName": t_obj.name,
                    "subjectsCovered": list(rm["subjects"]),
                    "sessions": rm["sessionsCount"],
                    "present": rm["present"],
                    "absent": max(0, rm["expected"] - rm["present"]),
                    "attendancePct": round((rm["present"] / rm["expected"]) * 100, 1) if rm["expected"] > 0 else 0
                })
                
        results.sort(key=lambda x: x["sessions"], reverse=True)
        return results
    except Exception as e:
        print(f"Error in teachers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


