import sys
import os

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database.database import SessionLocal, engine, Base
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.admin import Admin
from app.models.subject import Subject
from app.models.department import Department
from app.models.batch import Batch
from app.models.reference import Semester, Section
from app.models.timetable import TeacherAssignment

DEPARTMENTS = [
    {"name": "Information Technology", "code": "IT"},
    {"name": "Computer Science & Engineering", "code": "CSE"},
    {"name": "Electronics & Communication", "code": "ECE"},
    {"name": "Mechanical Engineering", "code": "MECH"},
    {"name": "AI & Data Science", "code": "AIDS"},
    {"name": "Civil Engineering", "code": "CIVIL"},
    {"name": "Electrical & Electronics", "code": "EEE"},
]

BATCHES = [
    {"department_code": "IT", "batch_name": "2023-2027", "current_year": 2, "current_semester": 5, "sections_count": 5},
    {"department_code": "CSE", "batch_name": "2023-2027", "current_year": 2, "current_semester": 5, "sections_count": 5},
    {"department_code": "ECE", "batch_name": "2023-2027", "current_year": 2, "current_semester": 4, "sections_count": 5},
    {"department_code": "MECH", "batch_name": "2022-2026", "current_year": 3, "current_semester": 6, "sections_count": 5},
    {"department_code": "AIDS", "batch_name": "2024-2028", "current_year": 1, "current_semester": 3, "sections_count": 5},
    {"department_code": "CIVIL", "batch_name": "2024-2028", "current_year": 1, "current_semester": 1, "sections_count": 5},
    {"department_code": "EEE", "batch_name": "2025-2029", "current_year": 1, "current_semester": 1, "sections_count": 5},
]

SEMESTERS = [{"id": i, "name": f"Semester {i}"} for i in range(1, 9)]

SECTIONS = [
    {"id": "A", "name": "Section A"},
    {"id": "B", "name": "Section B"},
    {"id": "C", "name": "Section C"},
    {"id": "D", "name": "Section D"},
]

SAMPLE_STUDENTS_MAPPINGS = [
    {"roll_no": "2023PECIT001", "name": "Arun Kumar", "email": "arun.kumar@example.com", "phone": "+91 9876543210", "dept_code": "IT", "batch_name": "2023-2027", "semester": 5, "section": "A", "academic_year": "2023-2027", "status": "active"},
    {"roll_no": "2023PECIT002", "name": "Priya Devi", "email": "priya.devi@example.com", "phone": "+91 9876543211", "dept_code": "IT", "batch_name": "2023-2027", "semester": 5, "section": "A", "academic_year": "2023-2027", "status": "active"},
    {"roll_no": "2023PECCSE001", "name": "Ananya Sharma", "email": "ananya.sharma@example.com", "phone": "+91 9876543213", "dept_code": "CSE", "batch_name": "2023-2027", "semester": 5, "section": "A", "academic_year": "2023-2027", "status": "active"},
    {"roll_no": "2022PECMECH001", "name": "Siddharth Verma", "email": "siddharth.v@example.com", "phone": "+91 9876543218", "dept_code": "MECH", "batch_name": "2022-2026", "semester": 6, "section": "A", "academic_year": "2022-2026", "status": "active"},
]

SAMPLE_TEACHERS_MAPPINGS = [
    {"employee_id": "EMP001", "name": "Dr. Venkatesh Kumar", "email": "venkatesh@example.com", "phone": "+91 9876500001", "dept_code": "IT", "designation": "Professor", "status": "active"},
    {"employee_id": "EMP002", "name": "Prof. Anitha Rao", "email": "anitha@example.com", "phone": "+91 9876500002", "dept_code": "CSE", "designation": "Assistant Professor", "status": "active"},
]

SAMPLE_SUBJECTS_MAPPINGS = [
    {"subject_code": "IT501", "subject_name": "Database Management Systems", "dept_code": "IT", "academic_year": "2026-2027", "semester": 5, "subject_type": "theory", "credits": 4, "status": "active", "description": "Relational database concepts and SQL"},
    {"subject_code": "CS501", "subject_name": "Artificial Intelligence", "dept_code": "CSE", "academic_year": "2026-2027", "semester": 5, "subject_type": "theory", "credits": 4, "status": "active"},
]

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 1. Seed Reference Static
        for sem in SEMESTERS:
            if not db.query(Semester).filter(Semester.id == sem["id"]).first():
                db.add(Semester(**sem))
        for sec in SECTIONS:
            if not db.query(Section).filter(Section.id == sec["id"]).first():
                db.add(Section(**sec))
        db.commit()

        # 2. Seed Dynamic Reference (Departments & Batches)
        dept_map = {}
        for d in DEPARTMENTS:
            db_dept = db.query(Department).filter(Department.code == d["code"]).first()
            if not db_dept:
                db_dept = Department(**d)
                db.add(db_dept)
                db.commit()
            dept_map[d["code"]] = db_dept.id

        batch_map = {}
        for b in BATCHES:
            dept_id = dept_map[b["department_code"]]
            db_batch = db.query(Batch).filter(Batch.department_id == dept_id, Batch.batch_name == b["batch_name"]).first()
            if not db_batch:
                b_copy = b.copy()
                del b_copy["department_code"]
                b_copy["department_id"] = dept_id
                db_batch = Batch(**b_copy)
                db.add(db_batch)
                db.commit()
            batch_map[(b["department_code"], b["batch_name"])] = db_batch.id

        # 3. Seed Students
        for s in SAMPLE_STUDENTS_MAPPINGS:
            if not db.query(Student).filter(Student.roll_no == s["roll_no"]).first():
                db.add(Student(
                    roll_no=s["roll_no"],
                    name=s["name"],
                    email=s["email"],
                    phone=s["phone"],
                    department_id=dept_map[s["dept_code"]],
                    batch_id=batch_map[(s["dept_code"], s["batch_name"])],
                    semester=s["semester"],
                    section=s["section"],
                    academic_year=s["academic_year"],
                    status=s["status"]
                ))
        db.commit()

        # 4. Seed Teachers
        for t in SAMPLE_TEACHERS_MAPPINGS:
            if not db.query(Teacher).filter(Teacher.employee_id == t["employee_id"]).first():
                db.add(Teacher(
                    employee_id=t["employee_id"],
                    name=t["name"],
                    email=t["email"],
                    phone=t["phone"],
                    department_id=dept_map[t["dept_code"]],
                    designation=t["designation"],
                    status=t["status"]
                ))
        db.commit()

        # 5. Seed Subjects
        subj_inserted = 0
        for subj in SAMPLE_SUBJECTS_MAPPINGS:
            existing = db.query(Subject).filter(
                Subject.subject_code == subj["subject_code"],
                Subject.department_id == dept_map[subj["dept_code"]],
                Subject.academic_year == subj["academic_year"],
                Subject.semester == subj["semester"],
            ).first()
            if not existing:
                s_copy = subj.copy()
                s_copy["department_id"] = dept_map[subj["dept_code"]]
                del s_copy["dept_code"]
                db.add(Subject(**s_copy))
                subj_inserted += 1
        db.commit()

        # 6. Seed Admin
        admin_email = "admin@pec.edu"
        existing_admin = db.query(Admin).filter(Admin.email == admin_email).first()
        if not existing_admin:
            db.add(Admin(
                email=admin_email,
                password="admin",
                name="System Administrator"
            ))

        db.commit()
        print(f"Seeded Admin, Departments, Batches, Students and Teachers.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    seed()
