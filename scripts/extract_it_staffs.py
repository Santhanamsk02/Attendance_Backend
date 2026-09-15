import sys
import os
import csv
from sqlalchemy.orm import Session

# Add the parent directory to sys.path so we can import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.teacher import Teacher
from app.models.department import Department

def extract_it_staffs():
    engine = create_engine('sqlite:///attendance.db')
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # Query IT department
        it_dept = db.query(Department).filter(Department.code == 'IT').first()
        
        if not it_dept:
            print("IT department not found in the database.")
            return

        # Query all teachers in IT department
        teachers = db.query(Teacher).filter(Teacher.department_id == it_dept.id).all()
        
        # Prepare CSV data
        csv_filename = "it_staffs.csv"
        csv_filepath = os.path.join(os.path.dirname(__file__), '..', csv_filename)
        
        with open(csv_filepath, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            # Write header
            writer.writerow(['employee_id', 'name', 'email', 'phone', 'department', 'designation', 'status'])
            
            # Write rows
            for teacher in teachers:
                writer.writerow([
                    teacher.employee_id,
                    teacher.name,
                    teacher.email,
                    teacher.phone,
                    it_dept.code,
                    teacher.designation,
                    teacher.status
                ])
                
        print(f"Successfully exported {len(teachers)} IT staff(s) to {csv_filepath}")
        
    finally:
        db.close()

if __name__ == "__main__":
    extract_it_staffs()
