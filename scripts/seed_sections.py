import sys
import os

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database.database import SessionLocal
from app.models.reference import Section

def seed_sections():
    db = SessionLocal()
    try:
        # Create sections A through Z
        for i in range(26):
            sec_char = chr(65 + i)
            sec = db.query(Section).filter(Section.id == sec_char).first()
            if not sec:
                db.add(Section(id=sec_char, name=f"Section {sec_char}"))
        
        db.commit()
        print("Successfully seeded all sections (A through Z) in the database.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding sections: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_sections()
