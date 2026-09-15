from app.database.database import SessionLocal
from app.models.student import Student, StudentEnrollment
from app.models.reference import AcademicYear

db = SessionLocal()

print("Students:", db.query(Student).count())
print("Active Students:", db.query(Student).filter(Student.status == "active").count())
print("Enrollments:", db.query(StudentEnrollment).count())
print("Academic Years:", db.query(AcademicYear).count())
