import sys
import os

# Add backend root to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database.database import SessionLocal, engine, Base
from app.models.teacher import Teacher

SAMPLE_TEACHERS = [
    {
        "employee_id": "EMP001",
        "name": "Dr. Kumar",
        "email": "kumar@example.com",
        "phone": "9876543210",
        "department": "IT",
        "designation": "Assistant Professor",
        "status": "active"
    },
    {
        "employee_id": "EMP002",
        "name": "Dr. Priya",
        "email": "priya@example.com",
        "phone": "9876543211",
        "department": "IT",
        "designation": "Professor",
        "status": "active"
    },
    {
        "employee_id": "EMP003",
        "name": "Rahul Kumar",
        "email": "rahul@example.com",
        "phone": "9876543212",
        "department": "CSE",
        "designation": "Lecturer",
        "status": "active"
    },
    {
        "employee_id": "EMP004",
        "name": "Meena",
        "email": "meena@example.com",
        "phone": "9876543213",
        "department": "ECE",
        "designation": "Assistant Professor",
        "status": "active"
    },
    {
        "employee_id": "EMP005",
        "name": "Arun",
        "email": "arun@example.com",
        "phone": "9876543214",
        "department": "IT",
        "designation": "Assistant Professor",
        "status": "active"
    }
]


def seed():
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        for data in SAMPLE_TEACHERS:
            existing = db.query(Teacher).filter(Teacher.employee_id == data["employee_id"]).first()
            if not existing:
                teacher = Teacher(**data)
                db.add(teacher)
                inserted += 1
            else:
                skipped += 1
        db.commit()
        print(f"Successfully seeded database: {inserted} inserted, {skipped} already existed.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
