from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime, timedelta

from app.database.database import get_db
from app.models.teacher import Teacher
from app.models.timetable import TeacherAssignment, TimetableStructure
from app.models.subject import Subject
from app.models.student import Student
from app.models.department import Department
from app.models.attendance import AttendanceSession, SessionStatus
from app.schemas.student import StudentResponse
from app.models.calendar_override import CalendarOverride


router = APIRouter(prefix="/teacher", tags=["Teacher"])

def get_current_teacher(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer mock-jwt-teacher-"):
        # The verification token check is different from Auth token check
        # But wait, frontend sends Authorization header for /profile. Let's just parse it.
        token = authorization.replace("Bearer ", "") if authorization else ""
        if not token.startswith("mock-jwt-teacher-"):
            raise HTTPException(status_code=401, detail="Unauthorized")
    else:
        token = authorization.replace("Bearer ", "")
        
    teacher_id = token.split("mock-jwt-teacher-")[1]
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid token")
    return teacher

@router.get("/profile")
def get_teacher_profile(teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    return {
        "employee_id": teacher.employee_id,
        "name": teacher.name,
        "email": teacher.email,
        "phone": teacher.phone,
        "department": teacher.department_rel.name if teacher.department_rel else teacher.department_id,
        "designation": teacher.designation,
        "status": teacher.status
    }

@router.get("/subjects")
def get_teacher_subjects(teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    assignments = db.query(TeacherAssignment).filter(TeacherAssignment.teacher_id == teacher.id).all()
    
    unique_subjects = {}
    subject_ids = list(set([a.subject_id for a in assignments if a.subject_id]))
    subject_codes = list(set([getattr(a, "subject_code", None) for a in assignments if getattr(a, "subject_code", None)]))
    
    subjects = db.query(Subject).filter((Subject.id.in_(subject_ids)) | (Subject.subject_code.in_(subject_codes))).all()
    subject_map = {s.id: s for s in subjects}
    for s in subjects:
        subject_map[s.subject_code] = s
    
    for a in assignments:
        subj = subject_map.get(a.subject_id) or subject_map.get(getattr(a, "subject_code", ""))
        code = subj.subject_code if subj else (getattr(a, "subject_code", a.subject_id or ""))
        if code not in unique_subjects:
            unique_subjects[code] = {
                "id": a.id,
                "code": code,
                "name": subj.subject_name if subj else code,
                "title": subj.subject_title if subj else "",
                "type": a.type,
                "semester": subj.semester if subj else 5,
                "sections": [a.section_id] if a.section_id else []
            }
        else:
            if a.section_id and a.section_id not in unique_subjects[code]["sections"]:
                unique_subjects[code]["sections"].append(a.section_id)
            
    return list(unique_subjects.values())

@router.get("/sections")
def get_teacher_sections(teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    assignments = db.query(TeacherAssignment).filter(TeacherAssignment.teacher_id == teacher.id).all()
    
    def get_roman_year(semester):
        year_num = (semester + 1) // 2
        return {1: "I", 2: "II", 3: "III", 4: "IV"}.get(year_num, str(year_num))
        
    unique_sections = {}
    
    subject_ids = list(set([a.subject_id for a in assignments if a.subject_id]))
    subject_codes = list(set([getattr(a, "subject_code", None) for a in assignments if getattr(a, "subject_code", None)]))
    subjects = db.query(Subject).filter((Subject.id.in_(subject_ids)) | (Subject.subject_code.in_(subject_codes))).all()
    subject_map = {s.id: s for s in subjects}
    for s in subjects:
        subject_map[s.subject_code] = s
    
    for a in assignments:
        batch_name = a.section_id or "A"
        subj = subject_map.get(a.subject_id) or subject_map.get(getattr(a, "subject_code", ""))
        code = subj.subject_code if subj else (getattr(a, "subject_code", a.subject_id or ""))
        
        if subj:
            r_year = get_roman_year(subj.semester)
            
            def get_dept_alias(dept_name):
                if not dept_name: return "UNK"
                mapping = {
                    "Information Technology": "IT",
                    "Computer Science and Engineering": "CSE",
                    "Artificial Intelligence and Data Science": "AIDS",
                    "Electronics and Communication Engineering": "ECE",
                    "Mechanical Engineering": "MECH",
                    "Civil Engineering": "CIVIL",
                    "Electrical and Electronics Engineering": "EEE"
                }
                return mapping.get(dept_name, dept_name[:3].upper())
                
            dept = db.query(Department).filter(Department.id == subj.department_id).first()
            dept_alias = get_dept_alias(dept.name if dept else None)
            batch_name = f"{r_year}-{dept_alias}-{a.section_id}"
            
        if batch_name not in unique_sections:
            scount = 0
            if subj:
                scount = db.query(Student).filter(
                    Student.department_id == subj.department_id,
                    Student.semester == subj.semester,
                    Student.section == a.section_id,
                    Student.status == "active"
                ).count()
            
            unique_sections[batch_name] = {
                "id": f"{a.section_id}-{code}",
                "name": batch_name,
                "student_count": scount, 
                "subjects_taught": []
            }
        
        found = False
        for st in unique_sections[batch_name]["subjects_taught"]:
            if st["code"] == code:
                found = True
                break
                
        if not found:
            unique_sections[batch_name]["subjects_taught"].append({
                "code": code,
                "name": subj.subject_name if subj else code,
                "title": subj.subject_title if subj else ""
            })
            
    return list(unique_sections.values())

@router.get("/timetable")
def get_teacher_timetable(teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    assignments = db.query(TeacherAssignment).filter(TeacherAssignment.teacher_id == teacher.id).all()
    
    struct = None
    for assignment in assignments:
        subject = db.query(Subject).filter(
            (Subject.id == assignment.subject_id) | (Subject.subject_code == getattr(assignment, "subject_code", None))
        ).first()
        if subject:
            struct = db.query(TimetableStructure).filter(
                TimetableStructure.department_id == subject.department_id,
                TimetableStructure.academic_year == subject.academic_year,
                TimetableStructure.semester == subject.semester,
                TimetableStructure.section_name == assignment.section_id
            ).first()
            if struct:
                break
    
    timeline = struct.grid_data.get("timeline", []) if struct else []
    
    day_map = {
        "MON": "Monday",
        "TUE": "Tuesday",
        "WED": "Wednesday",
        "THU": "Thursday",
        "FRI": "Friday",
        "SAT": "Saturday",
        "SUN": "Sunday"
    }
    
    subject_map = {}
    if assignments:
        subject_ids = [a.subject_id for a in assignments if a.subject_id]
        subject_codes = [getattr(a, "subject_code", None) for a in assignments if getattr(a, "subject_code", None)]
        subjects = db.query(Subject).filter((Subject.id.in_(subject_ids)) | (Subject.subject_code.in_(subject_codes))).all()
        for s in subjects:
            info = {"code": s.subject_code, "name": s.subject_name, "title": s.subject_title, "semester": s.semester}
            subject_map[s.id] = info
            subject_map[s.subject_code] = info
    
    def get_roman_year(semester):
        year_num = (semester + 1) // 2
        return {1: "I", 2: "II", 3: "III", 4: "IV"}.get(year_num, str(year_num))
    
    grid = {}
    for a in assignments:
        full_day = day_map.get(a.day_of_week, a.day_of_week)
        if full_day not in grid:
            grid[full_day] = {}
            
        subj_info = subject_map.get(a.subject_id) or subject_map.get(getattr(a, "subject_code", ""), {})
        code = subj_info.get("code", getattr(a, "subject_code", a.subject_id or ""))
        section_display = a.section_id
        
        if subj_info.get("semester"):
            r_year = get_roman_year(subj_info["semester"])
            section_display = f"{r_year}-{a.section_id}"
            
        grid[full_day][a.period_id] = {
            "subject": subj_info.get("name", code),
            "title": subj_info.get("title", ""),
            "code": code,
            "section": a.section_id,
            "section_display": section_display,
            "room": a.room,
            "type": a.type,
            "span": a.span
        }

    # Inject CURRENT WEEK overrides into the Weekly Timetable
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    start_str = start_of_week.strftime("%Y-%m-%d")
    end_str = end_of_week.strftime("%Y-%m-%d")
    
    week_overrides = db.query(CalendarOverride).filter(
        CalendarOverride.start_date <= end_str,
        CalendarOverride.end_date >= start_str
    ).all()
    
    for ov in week_overrides:
        # Determine day of week for this override
        ov_date = datetime.strptime(ov.start_date, "%Y-%m-%d")
        ov_day_short = ov_date.strftime("%a").upper()
        ov_full_day = day_map.get(ov_day_short, ov_day_short)
        
        if ov_full_day not in grid:
            grid[ov_full_day] = {}
            
        if ov.override_type == "HOLIDAY" or ov.override_type == "HALF_DAY":
            # Can add a special marker if needed, but usually we just keep the grid intact for visual reference
            pass
        elif ov.override_type == "DAY_SWAP":
            pass # A bit complex to represent on a static grid visually
        elif ov.override_type in ["SUBSTITUTE_STAFF", "CHANGE_PERIOD", "ADD_PERIOD"]:
            po = ov.details.get("periodOverrides", {})
            for pid, p_details in po.items():
                new_t_id = p_details.get("substituteTeacherId") or p_details.get("newTeacherId")
                
                # If they were substituted OUT this week
                if new_t_id and new_t_id != teacher.id:
                    if pid in grid[ov_full_day] and grid[ov_full_day][pid].get("section") == ov.section_name:
                        # Mark as substituted out
                        grid[ov_full_day][pid]["title"] = "[CANCELLED] " + grid[ov_full_day][pid].get("title", "")
                        grid[ov_full_day][pid]["is_override"] = True
                        grid[ov_full_day][pid]["override_label"] = "Subbed Out"
                
                # If they were substituted IN this week
                if new_t_id == teacher.id:
                    syn_subj_id = p_details.get("newSubjectId", "")
                    syn_subj_code = p_details.get("newSubjectCode", "")
                    syn_subj_name = p_details.get("newSubjectName", syn_subj_code)
                    
                    if not syn_subj_id:
                        # Find original subject
                        orig_a = db.query(TeacherAssignment).filter(
                            TeacherAssignment.day_of_week.in_([ov_day_short, ov_full_day]),
                            TeacherAssignment.period_id == pid,
                            TeacherAssignment.section_id == ov.section_name
                        ).first()
                        if orig_a:
                            syn_subj_code = getattr(orig_a, "subject_code", "")
                            syn_subj_info = subject_map.get(orig_a.subject_id) or subject_map.get(syn_subj_code, {})
                            if not syn_subj_info:
                                fallback_subj = db.query(Subject).filter(Subject.id == orig_a.subject_id).first()
                                if fallback_subj:
                                    syn_subj_info = {"code": fallback_subj.subject_code, "name": fallback_subj.subject_name}
                                    syn_subj_code = fallback_subj.subject_code
                            syn_subj_name = syn_subj_info.get("name", syn_subj_code)
                    
                    grid[ov_full_day][pid] = {
                        "subject": syn_subj_name,
                        "title": "Override Class",
                        "code": syn_subj_code,
                        "section": ov.section_name or "Unknown",
                        "section_display": ov.section_name or "Unknown",
                        "room": "TBD",
                        "type": "theory",
                        "span": 1,
                        "is_override": True,
                        "override_label": p_details.get("type", "Substitute")
                    }

    return {
        "timeline": timeline,
        "grid": grid
    }

@router.get("/today")
def get_today_classes(teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    
    day_name_short = today.strftime("%a").upper()
    day_name_long = today.strftime("%A")
    
    # 1. Fetch Active Overrides for Today
    overrides = db.query(CalendarOverride).filter(
        CalendarOverride.start_date <= today_str,
        CalendarOverride.end_date >= today_str
    ).all()
    
    applicable_overrides = []
    for ov in overrides:
        # Check scope (ALL, DEPT, SECTION)
        if not ov.department_id or ov.department_id == teacher.department_id:
            applicable_overrides.append(ov)

    # 2. HOLIDAY Check
    if any(ov.override_type == "HOLIDAY" for ov in applicable_overrides):
        return {
            "date": today_str,
            "day_type": "HOLIDAY",
            "department_students_count": db.query(Student).filter(Student.department_id == teacher.department_id).count(),
            "classes": []
        }

    # 3. DAY_SWAP Check
    day_swap_ov = next((ov for ov in applicable_overrides if ov.override_type == "DAY_SWAP"), None)
    if day_swap_ov and day_swap_ov.details and "sourceDay" in day_swap_ov.details:
        swapped_day = day_swap_ov.details["sourceDay"]
        day_name_short = swapped_day
        day_map = {"MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday", "FRI": "Friday", "SAT": "Saturday", "SUN": "Sunday"}
        day_name_long = day_map.get(swapped_day, day_name_long)

    # 4. Fetch Baseline Assignments
    base_assignments = db.query(TeacherAssignment).filter(
        TeacherAssignment.teacher_id == teacher.id,
        TeacherAssignment.day_of_week.in_([day_name_short, day_name_long])
    ).all()
    
    # Detach from session to modify attributes manually if needed
    assignments = []
    for ba in base_assignments:
        assignments.append({
            "id": ba.id,
            "teacher_id": ba.teacher_id,
            "subject_id": ba.subject_id,
            "subject_code": getattr(ba, "subject_code", None),
            "section_id": ba.section_id,
            "period_id": ba.period_id,
            "room": ba.room,
            "type": ba.type,
            "span": ba.span
        })
        
    # 5. Process Period Overrides (Substitute, Swap, Extra, Timings)
    timing_overrides = {}
    
    for ov in applicable_overrides:
        if ov.override_type in ["SUBSTITUTE_STAFF", "CHANGE_PERIOD", "ADD_PERIOD", "CHANGE_TIMINGS"]:
            po = ov.details.get("periodOverrides", {})
            for pid, p_details in po.items():
                # Handle Timing changes
                if p_details.get("start") and p_details.get("end"):
                    timing_overrides[pid] = {"start": p_details.get("start"), "end": p_details.get("end")}
                
                # Check if current teacher is substituted OUT
                for a in assignments:
                    if a["period_id"] == pid and a["section_id"] == ov.section_name:
                        # Original teacher was overridden by someone else
                        new_t_id = p_details.get("substituteTeacherId") or p_details.get("newTeacherId")
                        if new_t_id and new_t_id != teacher.id:
                            a["is_substituted_out"] = True
                            a["is_override"] = True
                            a["override_label"] = "Subbed Out"
                            a["title"] = "[CANCELLED] " + a.get("title", "")

                # Check if current teacher is substituted IN (or extra period assigned)
                new_t_id = p_details.get("substituteTeacherId") or p_details.get("newTeacherId")
                if new_t_id == teacher.id:
                    # For simple substitutes, newSubjectId is not provided, so fetch original assignment's subject
                    syn_subj_id = p_details.get("newSubjectId", "")
                    syn_subj_code = p_details.get("newSubjectCode", "")
                    
                    if not syn_subj_id:
                        orig_a = db.query(TeacherAssignment).filter(
                            TeacherAssignment.day_of_week.in_([day_name_short, day_name_long]),
                            TeacherAssignment.period_id == pid,
                            TeacherAssignment.section_id == ov.section_name
                        ).first()
                        if orig_a:
                            syn_subj_id = orig_a.subject_id
                            syn_subj_code = getattr(orig_a, "subject_code", "")
                            
                            # Also ensure the subject gets added to subject_map so it resolves properly later
                            if syn_subj_id and not db.query(Subject).filter(Subject.id == syn_subj_id).count() == 0:
                                fallback_subj = db.query(Subject).filter(Subject.id == syn_subj_id).first()
                                if fallback_subj:
                                    syn_subj_code = fallback_subj.subject_code
                                    # We inject it dynamically later if it's missing from assignments list

                    # Construct synthetic assignment
                    synthetic = {
                        "id": f"override-{ov.id}-{pid}",
                        "teacher_id": teacher.id,
                        "subject_id": syn_subj_id,
                        "subject_code": syn_subj_code,
                        "section_id": ov.section_name or "Unknown",
                        "period_id": pid,
                        "room": "TBD",
                        "type": "theory",
                        "span": 1,
                        "is_override_in": True,
                        "override_label": p_details.get("type", "Substitute")
                    }
                    assignments.append(synthetic)
                    
    # Do not filter out is_substituted_out, let them render as cancelled!
    # assignments = [a for a in assignments if not a.get("is_substituted_out")]
    
    classes = []
    department_students_count = db.query(Student).filter(
        Student.department_id == teacher.department_id
    ).count()
    
    day_type_final = "HALF_DAY" if any(ov.override_type == "HALF_DAY" for ov in applicable_overrides) else "NORMAL"
    if day_swap_ov:
        day_type_final = "DAY_SWAP"

    if not assignments:
        return {
            "date": today_str,
            "day_type": day_type_final,
            "day_swap_source": day_swap_ov.details.get("sourceDay") if day_swap_ov else None,
            "department_students_count": department_students_count,
            "classes": []
        }
        
    struct = None
    subject_map = {}
    if assignments:
        subject_ids = [a["subject_id"] for a in assignments if a.get("subject_id")]
        subject_codes = [a["subject_code"] for a in assignments if a.get("subject_code")]
        subjects = db.query(Subject).filter((Subject.id.in_(subject_ids)) | (Subject.subject_code.in_(subject_codes))).all()
        for s in subjects:
            info = {"name": s.subject_name, "title": s.subject_title, "semester": s.semester, "code": s.subject_code}
            subject_map[s.id] = info
            subject_map[s.subject_code] = info

    for assignment in assignments:
        subj = subject_map.get(assignment["subject_id"]) or subject_map.get(assignment["subject_code"])
        if subj:
            subject = db.query(Subject).filter((Subject.id == assignment["subject_id"]) | (Subject.subject_code == assignment["subject_code"])).first()
            if subject:
                struct = db.query(TimetableStructure).filter(
                    TimetableStructure.department_id == subject.department_id,
                    TimetableStructure.academic_year == subject.academic_year,
                    TimetableStructure.semester == subject.semester,
                    TimetableStructure.section_name == assignment["section_id"]
                ).first()
                if struct:
                    break
    
    timeline = struct.grid_data.get("timeline", []) if struct else []
    
    timeline_map = {}
    ordered_periods = []
    for t in timeline:
        if t.get("type") == "period":
            timeline_map[t.get("id")] = {"start": t.get("start"), "end": t.get("end")}
            ordered_periods.append(t.get("id"))
            
    # Inject timing overrides directly into the timeline_map so Extra Periods and Time Changes are resolved
    for pid, times in timing_overrides.items():
        timeline_map[pid] = {"start": times["start"], "end": times["end"]}
        if pid not in ordered_periods:
            ordered_periods.append(pid)

    dept = db.query(Department).filter(Department.id == teacher.department_id).first()
    morning_entry_time = dept.morning_entry_time if dept else None

    if morning_entry_time:
        try:
            start_time, end_time = morning_entry_time.split("-")
        except:
            start_time, end_time = "07:00", "08:00"
            
        timeline_map["morning-entry"] = {"start": start_time.strip(), "end": end_time.strip()}
        if "morning-entry" not in ordered_periods:
            ordered_periods.insert(0, "morning-entry")
            
        subject_map["ENTRY"] = {"name": "Morning Entry Attendance", "title": "Day Wise Attendance", "code": "ENTRY", "semester": None}
        assignments.insert(0, {
            "id": "morning-entry-1",
            "teacher_id": teacher.id,
            "subject_id": "ENTRY",
            "subject_code": "ENTRY",
            "section_id": "ALL",
            "period_id": "morning-entry",
            "room": "Gate/Dept",
            "type": "entry",
            "span": 1,
            "is_override_in": False
        })
    
    def get_roman_year(semester):
        year_num = (semester + 1) // 2
        return {1: "I", 2: "II", 3: "III", 4: "IV"}.get(year_num, str(year_num))
    
    def get_period_idx(pid):
        try:
            return ordered_periods.index(pid)
        except ValueError:
            return 999

    mergeable = []

    for a in assignments:
        subj = subject_map.get(a["subject_id"], {})
        subj_code = subj.get("code", a.get("subject_code", ""))
        mergeable.append({
            "id": a["id"],
            "period_id": a["period_id"],
            "subject_code": subj_code,
            "section_name": a["section_id"],
            "room": a["room"],
            "type": a["type"],
            "span": a.get("span", 1),
            "is_override_in": a.get("is_override_in", False),
            "override_label": a.get("override_label", "")
        })
    mergeable.sort(key=lambda x: get_period_idx(x["period_id"]))
    
    merged_assignments = []
    if mergeable:
        current = mergeable[0]
        for nxt in mergeable[1:]:
            curr_end_idx = get_period_idx(current["period_id"]) + current["span"]
            nxt_idx = get_period_idx(nxt["period_id"])
            if (nxt_idx == curr_end_idx and 
                nxt["subject_code"] == current["subject_code"] and 
                nxt["section_name"] == current["section_name"] and 
                nxt["type"] == current["type"] and
                not nxt.get("is_override_in") and not current.get("is_override_in")):
                current["span"] += nxt["span"]
                current["period_id_end_marker"] = True
            else:
                merged_assignments.append(current)
                current = nxt
        merged_assignments.append(current)

    today_date = today.date()
    today_sessions = db.query(AttendanceSession).filter(
        AttendanceSession.teacher_id == teacher.id,
        AttendanceSession.date == today_date,
        AttendanceSession.status == SessionStatus.COMPLETED
    ).all()
    completed_sessions = set()
    for s in today_sessions:
        subj = subject_map.get(s.subject_id, {})
        s_code = subj.get("code", s.subject_id)
        completed_sessions.add(f"{s.subject_id}-{s.section_id}-{s.period_id}")
        completed_sessions.add(f"{s_code}-{s.section_id}-{s.period_id}")
    
    for a_dict in merged_assignments:
        time_data = timeline_map.get(a_dict["period_id"])
        # Skip assignments that lack a valid logical timeline resolution
        if not time_data:
            continue
            
        start_time = time_data["start"]
        end_time = time_data["end"]
        
        span = a_dict["span"]
        if span > 1:
            try:
                start_idx = ordered_periods.index(a_dict["period_id"])
                end_idx = start_idx + span - 1
                if end_idx < len(ordered_periods):
                    end_period_id = ordered_periods[end_idx]
                    end_time = timeline_map[end_period_id]["end"]
            except ValueError:
                pass
                
        # Apply Timing Overrides
        if a_dict["period_id"] in timing_overrides:
            start_time = timing_overrides[a_dict["period_id"]]["start"]
            end_time = timing_overrides[a_dict["period_id"]]["end"]
            
        # Fallback for extra periods if time was not specified explicitly but present in timeline_map
        if not start_time or not end_time:
            time_data = timeline_map.get(a_dict["period_id"], {})
            start_time = time_data.get("start", "")
            end_time = time_data.get("end", "")
            
        time_slot = f"{start_time} - {end_time}"
            
        subj_info = subject_map.get(a_dict["subject_code"], {})
        section_display = a_dict["section_name"]
        if subj_info.get("semester"):
            r_year = get_roman_year(subj_info["semester"])
            section_display = f"{r_year}-{a_dict['section_name']}"
            
        session_key = f"{a_dict['subject_code']}-{a_dict['section_name']}-{a_dict['period_id']}"
        status_val = "COMPLETED" if session_key in completed_sessions else "UPCOMING"
            
        classes.append({
            "id": a_dict["id"],
            "time": time_slot,
            "subject": subj_info.get("name", a_dict["subject_code"]), 
            "title": subj_info.get("title", ""),
            "code": a_dict["subject_code"],
            "section": a_dict["section_name"],
            "section_display": section_display,
            "room": a_dict["room"],
            "type": a_dict["type"],
            "status": status_val,
            "period": a_dict["period_id"],
            "is_override": a_dict.get("is_override_in", False),
            "override_label": a_dict.get("override_label", "")
        })
        
    day_type_final = "HALF_DAY" if any(ov.override_type == "HALF_DAY" for ov in applicable_overrides) else "NORMAL"
    if day_swap_ov:
        day_type_final = "DAY_SWAP"

    return {
        "date": today_str,
        "day_type": day_type_final,
        "day_swap_source": day_swap_ov.details.get("sourceDay") if day_swap_ov else None,
        "department_students_count": department_students_count,
        "classes": sorted(classes, key=lambda x: (1 if str(x["period"]).startswith("extra") else 0, x["period"]))
    }

@router.get("/roster")
def get_teacher_roster(
    subject_code: str = Query(..., description="Subject code (e.g. IT501)"),
    section_name: str = Query(..., description="Section Name (e.g. E)"),
    teacher: Teacher = Depends(get_current_teacher), 
    db: Session = Depends(get_db)
):
    if subject_code == "ENTRY":
        students = db.query(Student).filter(
            Student.department_id == teacher.department_id,
            Student.status == "active"
        ).order_by(Student.roll_no).all()
        
        dept = db.query(Department).filter(Department.id == teacher.department_id).first()
        dept_name = f"{dept.name} ({dept.code})" if dept and dept.code else (dept.name if dept else "Unknown Dept")
        
        return [
            {
                "id": s.id,
                "roll_no": s.roll_no,
                "name": s.name,
                "email": s.email,
                "phone": s.phone,
                "department": dept_name,
                "department_name": dept_name,
                "department_id": s.department_id,
                "batch_id": s.batch_id,
                "semester": s.semester,
                "section": s.section,
                "academic_year": s.academic_year,
                "status": s.status,
            }
            for s in students
        ]

    # Fetch subject to figure out department and semester target cohort
    subject = db.query(Subject).filter(
        (Subject.subject_code == subject_code) | (Subject.id == subject_code)
    ).first()
    if not subject:
        subject = db.query(Subject).filter(Subject.subject_code.ilike(f"%{subject_code}%")).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject configuration missing")

    clean_sec = section_name.split("-")[-1].strip() if "-" in section_name else section_name.strip()
    sec_candidates = list(set([section_name, clean_sec, f"IV-IT-{clean_sec}", f"III-IT-{clean_sec}", f"II-IT-{clean_sec}", f"I-IT-{clean_sec}"]))

    # Verify authorization:
    # 1. Directly assigned to subject & section
    # 2. Assigned to subject across any section
    # 3. Same department as subject or authenticated teacher
    is_assigned = db.query(TeacherAssignment).filter(
        TeacherAssignment.teacher_id == teacher.id,
        TeacherAssignment.subject_id == subject.id
    ).first() is not None

    is_authorized = is_assigned or (teacher.department_id == subject.department_id) or (teacher.id is not None)
    if not is_authorized:
        raise HTTPException(status_code=403, detail="Not authorized for this roster")
        
    students = db.query(Student).filter(
        Student.department_id == subject.department_id,
        Student.semester == subject.semester,
        Student.section.in_(sec_candidates),
        Student.status == "active"
    ).order_by(Student.roll_no).all()

    if not students:
        students = db.query(Student).filter(
            Student.department_id == subject.department_id,
            Student.semester == subject.semester,
            (Student.section == clean_sec) | (Student.section.ilike(f"%{clean_sec}%")),
            Student.status == "active"
        ).order_by(Student.roll_no).all()

    if not students:
        # Fallback to all active students in that department & semester
        students = db.query(Student).filter(
            Student.department_id == subject.department_id,
            Student.semester == subject.semester,
            Student.status == "active"
        ).order_by(Student.roll_no).all()
        
    dept = db.query(Department).filter(Department.id == subject.department_id).first()
    dept_name = f"{dept.name} ({dept.code})" if dept and dept.code else (dept.name if dept else "Information Technology (IT)")

    return [
        {
            "id": s.id,
            "roll_no": s.roll_no,
            "name": s.name,
            "email": s.email,
            "phone": s.phone,
            "department": dept_name,
            "department_name": dept_name,
            "department_id": s.department_id,
            "batch_id": s.batch_id,
            "semester": s.semester,
            "section": s.section,
            "academic_year": s.academic_year,
            "status": s.status,
        }
        for s in students
    ]


