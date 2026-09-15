import sys
import os

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database.database import SessionLocal
from app.models.admin import Admin

def create_admin():
    db = SessionLocal()
    try:
        admin_email = "admin@pec.edu"
        existing_admin = db.query(Admin).filter(Admin.email == admin_email).first()
        if not existing_admin:
            db.add(Admin(
                email=admin_email,
                password="admin",
                name="System Administrator"
            ))
            db.commit()
            print(f"Successfully created admin user: {admin_email} / admin")
        else:
            print(f"Admin user {admin_email} already exists.")
    except Exception as e:
        db.rollback()
        print(f"Error creating admin: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_admin()
