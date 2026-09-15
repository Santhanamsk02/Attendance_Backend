from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import date, timedelta
import io
import csv

from app.database.database import get_db
from app.models.student import Student
from app.models.day_wise_attendance import DayWiseAttendance
from app.models.attendance import AttendanceMark, AttendanceSession

router = APIRouter(prefix="/reports", tags=["Attendance Reports"])


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _to_date(d):
    if isinstance(d, str):
        return date.fromisoformat(d)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# 1. Dashboard cards + leaderboard
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def get_report_dashboard(db: Session = Depends(get_db)):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def pct_for_range(from_date, to_date):
        rows = db.execute(text("""
            SELECT COALESCE(SUM(present_count),0) AS p,
                   COALESCE(SUM(total_students),0) AS total
            FROM v_department_daily_summary
            WHERE att_date BETWEEN :from_d AND :to_d
        """), {"from_d": from_date.isoformat(), "to_d": to_date.isoformat()}).fetchone()
        total = int(rows[1]) if rows else 0
        present = int(rows[0]) if rows else 0
        if total > 0:
            return round(present / total * 100, 2)
        return None

    today_pct = pct_for_range(today, today)
    week_pct = pct_for_range(week_start, today)
    month_pct = pct_for_range(month_start, today)

    # Department summaries today
    dept_rows = db.execute(text("""
        SELECT department_id, department_name, 
               SUM(present_count) AS present, SUM(total_students) AS total
        FROM v_department_daily_summary
        WHERE att_date = :d
        GROUP BY department_id, department_name
    """), {"d": today.isoformat()}).fetchall()
    dept_today = [
        {
            "department_id": r.department_id,
            "department_name": r.department_name,
            "present": r.present,
            "total": r.total,
            "pct": round(r.present / r.total * 100, 2) if r.total else 0,
        }
        for r in dept_rows
    ]

    # Section leaderboard
    leaderboard = db.execute(text("""
        SELECT section, overall_pct, total_present, total_absent,
               working_days_recorded, rank_best_to_worst
        FROM v_section_leaderboard
        ORDER BY rank_best_to_worst
    """)).fetchall()
    leaderboard_data = [dict(r._mapping) for r in leaderboard]

    return {
        "summary": {
            "today_pct": today_pct,
            "week_pct": week_pct,
            "month_pct": month_pct,
        },
        "departments_today": dept_today,
        "leaderboard": leaderboard_data,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Daily Attendance Register
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/daily")
def get_daily_register(
    att_date: date = Query(..., alias="date"),
    section: Optional[str] = None,
    department_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    status: Optional[str] = None,   # "Present" | "Absent" | None (all)
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    # Base query — all active students matching the filters
    base_q = db.query(Student).filter(Student.status == "active")
    if section:
        base_q = base_q.filter(Student.section == section)
    if department_id:
        base_q = base_q.filter(Student.department_id == department_id)
    if batch_id:
        base_q = base_q.filter(Student.batch_id == batch_id)

    total = base_q.count()

    # Fetch ALL student IDs to compute accurate summary stats
    all_ids = [s.id for s in base_q.with_entities(Student.id).all()]

    # Who was present on this date?
    present_ids: set = set()
    if all_ids:
        marks_daywise = db.query(DayWiseAttendance.student_id).filter(
            DayWiseAttendance.date == att_date,
            DayWiseAttendance.student_id.in_(all_ids),
            DayWiseAttendance.status == "PRESENT"
        ).all()
        
        marks_session = db.query(AttendanceMark.student_id).join(
            AttendanceSession, AttendanceMark.session_id == AttendanceSession.id
        ).filter(
            AttendanceSession.date == att_date,
            AttendanceMark.student_id.in_(all_ids),
            AttendanceMark.status == "PRESENT"
        ).all()
        
        present_ids = {m.student_id for m in marks_daywise} | {m.student_id for m in marks_session}

    absent_ids = set(all_ids) - present_ids

    total_present = len(present_ids)
    total_absent = len(absent_ids)
    pct = round(total_present / total * 100, 2) if total > 0 else 0

    # Apply status filter: restrict which students appear in the table
    if status == "Present":
        filtered_ids = list(present_ids)
    elif status == "Absent":
        filtered_ids = list(absent_ids)
    else:
        filtered_ids = all_ids  # show everyone

    # Paginate only the filtered subset
    filtered_count = len(filtered_ids)
    from sqlalchemy.orm import joinedload
    from sqlalchemy import text

    if not filtered_ids:
        paginated_students = []
    else:
        paginated_students = (
            base_q
            .options(joinedload(Student.department_rel), joinedload(Student.batch_rel))
            .filter(Student.id.in_(filtered_ids))
            .order_by(Student.roll_no)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

    student_ids = [s.id for s in paginated_students]
    morning_entry_map = {}
    period_stats_map = {}

    if student_ids:
        from sqlalchemy import func, case

        # Fetch morning entry status
        morning_marks = (
            db.query(AttendanceMark.student_id, AttendanceMark.status)
            .join(AttendanceSession, AttendanceMark.session_id == AttendanceSession.id)
            .filter(
                AttendanceMark.student_id.in_(student_ids),
                AttendanceSession.date == att_date,
                AttendanceSession.period_id == 'morning-entry'
            ).all()
        )
        morning_entry_map = {row.student_id: row.status for row in morning_marks}
        
        # Fetch periods present/absent
        period_marks = (
            db.query(
                AttendanceMark.student_id,
                func.sum(case((AttendanceMark.status == 'PRESENT', 1), else_=0)).label('periods_present'),
                func.sum(case((AttendanceMark.status == 'ABSENT', 1), else_=0)).label('periods_absent')
            )
            .join(AttendanceSession, AttendanceMark.session_id == AttendanceSession.id)
            .filter(
                AttendanceMark.student_id.in_(student_ids),
                AttendanceSession.date == att_date,
                AttendanceSession.period_id != 'morning-entry'
            )
            .group_by(AttendanceMark.student_id)
            .all()
        )
        period_stats_map = {row.student_id: (row.periods_present or 0, row.periods_absent or 0) for row in period_marks}

        # Calculate Expected and Taken periods per section
        from app.models.timetable import TeacherAssignment
        dow = att_date.strftime('%A')[:3].upper()
        
        expected_q = db.query(
            TeacherAssignment.department_id,
            TeacherAssignment.batch_id,
            TeacherAssignment.section_id,
            func.count(TeacherAssignment.id)
        ).filter(TeacherAssignment.day_of_week == dow).group_by(
            TeacherAssignment.department_id, TeacherAssignment.batch_id, TeacherAssignment.section_id
        ).all()
        expected_map = {(r[0], r[1], r[2]): r[3] for r in expected_q}
        
        taken_q = db.query(
            AttendanceSession.department_id,
            AttendanceSession.batch_id,
            AttendanceSession.section_id,
            func.count(AttendanceSession.id)
        ).filter(
            AttendanceSession.date == att_date,
            AttendanceSession.period_id != 'morning-entry'
        ).group_by(
            AttendanceSession.department_id, AttendanceSession.batch_id, AttendanceSession.section_id
        ).all()
        taken_map = {(r[0], r[1], r[2]): r[3] for r in taken_q}
    else:
        expected_map = {}
        taken_map = {}

    rows = []
    for s in paginated_students:
        p_stats = period_stats_map.get(s.id, (0, 0))
        m_entry = morning_entry_map.get(s.id)
        
        key = (s.department_id, s.batch_id, s.section)
        present_count = p_stats[0]
        expected_count = expected_map.get(key, 0)
        taken_count = taken_map.get(key, taken_map.get((None, None, s.section), 0))
        
        absent_count = max(0, taken_count - present_count)
        not_taken_count = max(0, expected_count - taken_count)
        
        rows.append({
            "id": s.id,
            "roll_no": s.roll_no,
            "name": s.name,
            "section": s.section,
            "department": s.department_rel.code if s.department_rel else None,
            "year": s.semester,
            "batch": s.batch_rel.batch_name if s.batch_rel else None,
            "morning_entry": m_entry,
            "periods_present": present_count,
            "periods_absent": absent_count,
            "periods_not_taken": not_taken_count,
            "status": "Present" if s.id in present_ids else "Absent",
        })

    chart_data_map = {}
    
    # We need grouping metadata from all matching students to build the chart.
    from app.models.department import Department
    from app.models.batch import Batch
    
    meta_q = (
        base_q.with_entities(
            Student.id,
            Department.code,
            Batch.batch_name,
            Student.section
        )
        .outerjoin(Student.department_rel)
        .outerjoin(Student.batch_rel)
        .all()
    )

    if not department_id:
        group_key_index = 1 # Department.code
    elif not batch_id:
        group_key_index = 2 # Batch.batch_name
    else:
        group_key_index = 3 # Student.section

    for row in meta_q:
        sid, dept_code, batch_name, sec = row
        
        if group_key_index == 1:
            group_name = dept_code or "Unknown"
        elif group_key_index == 2:
            group_name = batch_name or "Unknown"
        else:
            group_name = f"Sec {sec}" if sec else "Unknown"
            
        if group_name not in chart_data_map:
            chart_data_map[group_name] = {"name": group_name, "Total": 0, "Present": 0, "Absent": 0}
            
        chart_data_map[group_name]["Total"] += 1
        if sid in present_ids:
            chart_data_map[group_name]["Present"] += 1
        else:
            chart_data_map[group_name]["Absent"] += 1

    chart_data = []
    for gd in chart_data_map.values():
        group_total = gd["Total"]
        gd["Present_Pct"] = round(gd["Present"] / group_total * 100, 2) if group_total else 0
        gd["Absent_Pct"] = round(gd["Absent"] / group_total * 100, 2) if group_total else 0
        chart_data.append(gd)

    chart_data.sort(key=lambda x: x["name"])

    return {
        "date": att_date.isoformat(),
        "section": section,
        "summary": {
            "present": total_present,
            "absent": total_absent,
            "total": total,
            "pct": pct,
        },
        "chart_data": chart_data,
        "total_records": filtered_count,
        "page": page,
        "page_size": page_size,
        "pages": (filtered_count + page_size - 1) // page_size if filtered_count else 1,
        "data": rows,
    }




@router.get("/daily/export")
def export_daily_register(
    att_date: date = Query(..., alias="date"),
    section: Optional[str] = None,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    data = get_daily_register(
        att_date=att_date, section=section, department_id=department_id,
        page=1, page_size=10000, db=db
    )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["roll_no", "name", "section", "status"])
    writer.writeheader()
    for row in data["data"]:
        writer.writerow({"roll_no": row["roll_no"], "name": row["name"],
                         "section": row["section"], "status": row["status"]})
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{att_date}.csv"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Student Profile Report
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/student/{student_id}")
def get_student_report(
    student_id: str,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.id == student_id, Student.status == "active").first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if not from_date:
        # Find the earliest date for the student's batch
        earliest_session = db.query(AttendanceSession.date).filter(
            AttendanceSession.batch_id == student.batch_id,
            AttendanceSession.status == "COMPLETED"
        ).order_by(AttendanceSession.date.asc()).first()
        if earliest_session:
            from_date = earliest_session.date
        else:
            from_date = date.today() - timedelta(days=89)
    if not to_date:
        to_date = date.today()

    # All day-wise marks in range
    marks_daywise = db.query(DayWiseAttendance).filter(
        DayWiseAttendance.student_id == student_id,
        DayWiseAttendance.date >= from_date,
        DayWiseAttendance.date <= to_date,
    ).all()
    present_dates = {m.date.isoformat() for m in marks_daywise if m.status == "PRESENT"}

    # Also check period-wise marks (AttendanceMark) in the same range
    marks_session = db.query(AttendanceSession.date).join(
        AttendanceMark, AttendanceMark.session_id == AttendanceSession.id
    ).filter(
        AttendanceMark.student_id == student_id,
        AttendanceMark.status == "PRESENT",
        AttendanceSession.date >= from_date,
        AttendanceSession.date <= to_date
    ).all()
    present_dates.update(m.date.isoformat() for m in marks_session)

    # Get working dates for the batch
    working_dates_query = db.query(AttendanceSession.date).filter(
        AttendanceSession.batch_id == student.batch_id,
        AttendanceSession.status == "COMPLETED",
        AttendanceSession.date >= from_date,
        AttendanceSession.date <= to_date
    ).distinct().all()
    working_dates = {m.date.isoformat() for m in working_dates_query}

    # Build heatmap: for each date in range
    heatmap = []
    d = from_date
    while d <= to_date:
        d_str = d.isoformat()
        if d_str in working_dates:
            status = "Present" if d_str in present_dates else "Absent"
        else:
            status = "N/A"
        heatmap.append({
            "date": d_str,
            "status": status,
        })
        d += timedelta(days=1)

    total_days = len(heatmap)
    present_count = len(present_dates)

    # Absence streak (most recent consecutive absences)
    streak = 0
    for entry in reversed(heatmap):
        if entry["status"] == "Absent":
            streak += 1
        elif entry["status"] == "Present":
            break

    # Calculate overall session stats for the student in this date range
    session_stats = db.execute(text("""
        SELECT COUNT(ass.id) AS total_sessions,
               SUM(CASE WHEN am.status = 'PRESENT' THEN 1 ELSE 0 END) AS present_sessions
        FROM attendance_sessions ass
        LEFT JOIN attendance_marks am ON am.session_id = ass.id AND am.student_id = :sid
        WHERE ass.status = 'COMPLETED'
          AND ass.department_id = :dept
          AND ass.section_id = :sec
          AND ass.date BETWEEN :f AND :t
    """), {
        "sid": student_id, 
        "f": from_date.isoformat(), 
        "t": to_date.isoformat(),
        "dept": student.department_id,
        "sec": student.section
    }).first()
    
    total_sessions = session_stats.total_sessions or 0
    present_sessions = session_stats.present_sessions or 0
    overall_pct = round((present_sessions / total_sessions * 100), 2) if total_sessions > 0 else 0

    # Subject-wise (best effort via resolvable sessions)
    subject_rows = db.execute(text("""
        SELECT sub.subject_name, sub.subject_code,
               COUNT(ass.id) AS total_sessions,
               SUM(CASE WHEN am.status = 'PRESENT' THEN 1 ELSE 0 END) AS present_sessions
        FROM attendance_sessions ass
        JOIN subjects sub ON ass.subject_id = sub.id
        LEFT JOIN attendance_marks am ON am.session_id = ass.id AND am.student_id = :sid
        WHERE ass.status = 'COMPLETED'
          AND ass.department_id = :dept
          AND ass.section_id = :sec
          AND ass.date BETWEEN :f AND :t
        GROUP BY sub.id, sub.subject_name, sub.subject_code
    """), {
        "sid": student_id, 
        "f": from_date.isoformat(), 
        "t": to_date.isoformat(),
        "dept": student.department_id,
        "sec": student.section
    }).fetchall()
    
    subject_wise = []
    for r in subject_rows:
        subject_wise.append({
            "subject_name": r.subject_name,
            "subject_code": r.subject_code,
            "total_sessions": r.total_sessions,
            "present_sessions": r.present_sessions,
            "pct": round((r.present_sessions or 0) / r.total_sessions * 100, 2) if r.total_sessions else 0,
        })

    return {
        "student": {
            "id": student.id,
            "roll_no": student.roll_no,
            "name": student.name,
            "section": student.section,
            "semester": student.semester,
            "department_id": student.department_id,
        },
        "summary": {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "total_days": total_days,
            "present_days": present_count,
            "absent_days": len(working_dates) - present_count,
            "total_sessions": total_sessions,
            "present_sessions": present_sessions,
            "absent_sessions": total_sessions - present_sessions,
            "overall_pct": overall_pct,
            "absence_streak": streak,
        },
        "heatmap": heatmap,
        "subject_wise": subject_wise,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Trend Analysis (Section / Batch / Dept)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/trends")
def get_trends(
    level: str = Query("section", enum=["section", "batch", "department"]),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    section: Optional[str] = None,
    batch_id: Optional[str] = None,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if not from_date:
        from_date = date.today() - timedelta(days=29)
    if not to_date:
        to_date = date.today()

    if level == "section":
        query = text("""
            SELECT section AS label, att_date, present_count, total_students, pct_present
            FROM v_section_daily_summary
            WHERE att_date BETWEEN :f AND :t
              AND (:s IS NULL OR section = :s)
            ORDER BY att_date
        """)
        rows = db.execute(query, {"f": from_date.isoformat(), "t": to_date.isoformat(), "s": section}).fetchall()

        # Also weekly trend for comparison
        weekly = db.execute(text("""
            SELECT section, week, week_start, present_count, total_students, pct_present
            FROM v_section_weekly_trend
            WHERE (:s IS NULL OR section = :s)
            ORDER BY week_start DESC
            LIMIT 20
        """), {"s": section}).fetchall()
        trend_weekly = [dict(r._mapping) for r in weekly]

    elif level == "batch":
        query = text("""
            SELECT batch_name AS label, att_date, present_count, total_students, pct_present
            FROM v_batch_daily_summary
            WHERE att_date BETWEEN :f AND :t
              AND (:b IS NULL OR batch_id = :b)
            ORDER BY att_date
        """)
        rows = db.execute(query, {"f": from_date.isoformat(), "t": to_date.isoformat(), "b": batch_id}).fetchall()
        trend_weekly = []

    else:  # department
        query = text("""
            SELECT department_name AS label, att_date, present_count, total_students, pct_present
            FROM v_department_daily_summary
            WHERE att_date BETWEEN :f AND :t
              AND (:d IS NULL OR department_id = :d)
            ORDER BY att_date
        """)
        rows = db.execute(query, {"f": from_date.isoformat(), "t": to_date.isoformat(), "d": department_id}).fetchall()
        trend_weekly = []

    daily = [dict(r._mapping) for r in rows]
    return {"level": level, "from_date": from_date.isoformat(), "to_date": to_date.isoformat(),
            "daily": daily, "weekly": trend_weekly}


@router.get("/summary")
def get_summary(
    level: str = Query("section", enum=["section", "batch", "department"]),
    db: Session = Depends(get_db),
):
    if level == "section":
        rows = db.execute(text("SELECT * FROM v_section_overall_summary ORDER BY overall_pct DESC")).fetchall()
    elif level == "batch":
        rows = db.execute(text("SELECT * FROM v_batch_overall_summary ORDER BY overall_pct DESC")).fetchall()
    else:
        rows = db.execute(text("SELECT * FROM v_department_overall_summary ORDER BY overall_pct DESC")).fetchall()
    return [dict(r._mapping) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Defaulter / Shortage Report
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/defaulters")
def get_defaulters(
    threshold: float = Query(75.0),
    department_id: Optional[str] = None,
    section: Optional[str] = None,
    batch_id: Optional[str] = None,
    query: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    # Compute per-student totals from day_wise_attendance
    base_sql = text("""
        SELECT s.id, s.roll_no, s.name, s.section, s.department_id, s.semester,
               s.email, s.phone,
               COUNT(DISTINCT CASE WHEN dwa.status = 'PRESENT' THEN dwa.date END) AS present_days,
               (SELECT COUNT(DISTINCT dwa2.date)
                FROM day_wise_attendance dwa2
                JOIN students s2 ON dwa2.student_id = s2.id
                WHERE s2.section = s.section
               ) AS total_working_days
        FROM students s
        LEFT JOIN day_wise_attendance dwa ON dwa.student_id = s.id
        WHERE s.status = 'active'
          AND (:dept IS NULL OR s.department_id = :dept)
          AND (:sec IS NULL OR s.section = :sec)
          AND (:batch IS NULL OR s.batch_id = :batch)
          AND (:query IS NULL OR (s.name ILIKE :query_like OR s.roll_no ILIKE :query_like))
        GROUP BY s.id
        HAVING total_working_days > 0
           AND ROUND(CAST(present_days AS FLOAT) / total_working_days * 100, 2) < :threshold
        ORDER BY ROUND(CAST(present_days AS FLOAT) / total_working_days * 100, 2)
    """)
    results = db.execute(base_sql, {
        "dept": department_id, "sec": section, "threshold": threshold,
        "batch": batch_id, "query": query, "query_like": f"%{query}%" if query else None
    }).fetchall()

    total = len(results)
    paginated = results[(page - 1) * page_size: page * page_size]

    data = []
    for r in paginated:
        pct = round(r.present_days / r.total_working_days * 100, 2) if r.total_working_days else 0
        # Shortage: days needed to reach threshold
        # (present + x) / (total + x) >= threshold/100
        # x >= (threshold * total - 100 * present) / (100 - threshold)
        needed = 0
        if threshold < 100:
            num = threshold * r.total_working_days - 100 * r.present_days
            den = 100 - threshold
            if num > 0:
                needed = int(-(-num // den))  # ceiling division
        data.append({
            "id": r.id,
            "roll_no": r.roll_no,
            "name": r.name,
            "section": r.section,
            "department_id": r.department_id,
            "semester": r.semester,
            "email": r.email,
            "phone": r.phone,
            "present_days": r.present_days,
            "total_working_days": r.total_working_days,
            "attendance_pct": pct,
            "days_needed": needed,
        })

    return {
        "threshold": threshold,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "data": data,
    }


@router.get("/defaulters/export")
def export_defaulters(
    threshold: float = Query(75.0),
    department_id: Optional[str] = None,
    section: Optional[str] = None,
    batch_id: Optional[str] = None,
    query: Optional[str] = None,
    db: Session = Depends(get_db),
):
    import csv
    import io

    data = get_defaulters(
        threshold=threshold,
        department_id=department_id,
        section=section,
        batch_id=batch_id,
        query=query,
        page=1,
        page_size=100000,
        db=db
    )
    output = io.StringIO()
    fields = ["roll_no", "name", "section", "semester", "email", "phone",
              "present_days", "total_working_days", "attendance_pct", "days_needed"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data["data"])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=defaulters_{int(threshold)}pct.csv"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Admin Data-Health Report
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/data-health")
def get_data_health(db: Session = Depends(get_db)):
    # Orphaned marks: attendance_marks with no matching session
    orphaned = db.execute(text("""
        SELECT COUNT(*) AS cnt
        FROM attendance_marks am
        LEFT JOIN attendance_sessions ass ON am.session_id = ass.id
        WHERE ass.id IS NULL
    """)).scalar()

    # Sections with partial rosters on recent dates (< 50% of enrolled marked)
    partial = db.execute(text("""
        SELECT s.section, dwa.date, 
               COUNT(DISTINCT dwa.student_id) AS marked_count,
               COUNT(DISTINCT s.id) AS enrolled_count,
               ROUND(CAST(COUNT(DISTINCT dwa.student_id) AS FLOAT) / COUNT(DISTINCT s.id) * 100, 1) AS coverage_pct
        FROM students s
        LEFT JOIN day_wise_attendance dwa ON dwa.student_id = s.id
        WHERE s.status = 'active' AND dwa.date >= date('now', '-30 days')
        GROUP BY s.section, dwa.date
        HAVING coverage_pct < 50 AND coverage_pct > 0
        ORDER BY dwa.date DESC
        LIMIT 30
    """)).fetchall()

    # Dates with attendance_marks but no session record
    orphan_dates = db.execute(text("""
        SELECT DATE(am.marked_at) AS mark_date, COUNT(*) AS mark_count
        FROM attendance_marks am
        LEFT JOIN attendance_sessions ass ON am.session_id = ass.id
        WHERE ass.id IS NULL AND am.marked_at IS NOT NULL
        GROUP BY mark_date
        ORDER BY mark_date DESC
        LIMIT 20
    """)).fetchall()

    return {
        "orphaned_marks_total": orphaned or 0,
        "partial_roster_sessions": [dict(r._mapping) for r in partial],
        "orphaned_marks_by_date": [dict(r._mapping) for r in orphan_dates],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. Student Day Analysis Modal Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/student/{student_id}/day-analysis")
def get_student_day_analysis(
    student_id: str,
    date: date = Query(...),
    db: Session = Depends(get_db)
):
    from app.models.student import Student
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    day_mapping = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}
    dow = day_mapping[date.weekday()]

    m_sql = text("""
        SELECT s.id AS session_id, m.id AS mark_id
        FROM attendance_sessions s
        LEFT JOIN attendance_marks m
          ON m.session_id = s.id AND m.student_id = :student_id AND m.status = 'PRESENT'
        WHERE s.date = :date AND s.period_id = 'morning-entry'
    """)
    m_res = db.execute(m_sql, {"student_id": student.id, "date": date}).first()
    
    morning_conducted = False
    morning_status = "NOT_CONDUCTED"
    if m_res and m_res.session_id:
        morning_conducted = True
        morning_status = "PRESENT" if m_res.mark_id else "ABSENT"

    p_sql = text("""
        WITH scheduled AS (
          SELECT ta.period_id, ta.span, ta.type, ta.subject_id, ta.teacher_id, sub.subject_name, t.name AS teacher_name
          FROM teacher_assignments ta
          JOIN subjects sub ON sub.id = ta.subject_id
          JOIN teachers t ON t.id = ta.teacher_id
          WHERE ta.department_id = :dept_id AND ta.batch_id = :batch_id AND ta.section_id = :section
            AND ta.day_of_week = :day_of_week
        ),
        sessions_that_day AS (
          SELECT id, period_id FROM attendance_sessions
          WHERE date = :date AND section_id = :section
            AND (department_id = :dept_id OR department_id IS NULL)
            AND (batch_id = :batch_id OR batch_id IS NULL)
        )
        SELECT
          sch.period_id, sch.span, sch.type, sch.subject_name, sch.teacher_name,
          CASE
            WHEN s.id IS NULL THEN 'NOT_TAKEN'
            WHEN m.id IS NOT NULL THEN 'PRESENT'
            ELSE 'ABSENT'
          END AS period_status
        FROM scheduled sch
        LEFT JOIN sessions_that_day s ON s.period_id = sch.period_id
        LEFT JOIN attendance_marks m ON m.session_id = s.id AND m.student_id = :student_id AND m.status = 'PRESENT'
        ORDER BY sch.period_id;
    """)
    periods = db.execute(p_sql, {
        "dept_id": student.department_id,
        "batch_id": student.batch_id,
        "section": student.section,
        "day_of_week": dow,
        "date": date,
        "student_id": student.id
    }).fetchall()

    d_sql = text("""
        SELECT status FROM day_wise_attendance WHERE student_id = :student_id AND date = :date
    """)
    d_res = db.execute(d_sql, {"student_id": student.id, "date": date}).first()
    day_status = d_res.status if d_res else "NO_DATA"

    all_not_taken = len(periods) > 0 and all(p.period_status == 'NOT_TAKEN' for p in periods)
    legacy_data_gap = day_status in ('PRESENT', 'ABSENT') and all_not_taken

    return {
        "student": {
            "id": student.id,
            "name": student.name,
            "roll_no": student.roll_no,
            "department": student.department_rel.code if student.department_rel else None,
            "batch": student.batch_rel.batch_name if student.batch_rel else None,
            "year": student.semester,
            "semester": student.semester,
            "section": student.section
        },
        "date": date.isoformat(),
        "day_status": day_status,
        "morning_entry": {
            "conducted": morning_conducted,
            "status": morning_status
        },
        "periods": [
            {
                "period_id": p.period_id,
                "span": p.span,
                "type": p.type,
                "time": f"Periods {int(p.period_id.split('-')[1])}–{int(p.period_id.split('-')[1]) + p.span - 1}" if p.span and p.span > 1 else p.period_id.capitalize().replace('-', ' '),
                "subject": p.subject_name,
                "teacher": p.teacher_name,
                "status": p.period_status
            }
            for p in periods
        ],
        "legacy_data_gap": legacy_data_gap
    }


# ─────────────────────────────────────────────────────────────────────────────
# Filters metadata (departments, sections list)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/meta/filters")
def get_filter_metadata(db: Session = Depends(get_db)):
    depts = db.execute(text("SELECT id, name, code FROM departments ORDER BY name")).fetchall()
    sections = db.execute(text(
        "SELECT DISTINCT section FROM students WHERE status='active' ORDER BY section"
    )).fetchall()
    semesters = db.execute(text(
        "SELECT DISTINCT semester FROM students WHERE status='active' ORDER BY semester"
    )).fetchall()
    batches = db.execute(text(
        "SELECT id, batch_name FROM batches ORDER BY batch_name"
    )).fetchall()

    return {
        "departments": [{"id": r.id, "name": r.name, "code": r.code} for r in depts],
        "sections": [r.section for r in sections],
        "semesters": [r.semester for r in semesters],
        "batches": [{"id": r.id, "name": r.batch_name} for r in batches],
    }
