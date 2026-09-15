from app.database.database import SessionLocal
from app.models.student import Student, StudentEnrollment
from app.models.reference import AcademicYear

db = SessionLocal()
q = db.query(Student, StudentEnrollment, AcademicYear).join(
    StudentEnrollment, Student.id == StudentEnrollment.student_id
).outerjoin(
    AcademicYear, StudentEnrollment.academic_year_id == AcademicYear.id
).filter(Student.status == "active")

print("Total records:", q.count())
try:
    records = q.limit(5).all()
    print("Records fetched:", len(records))
    for r in records:
        print(r)
except Exception as e:
    print("Error:", e)
