import sys
import os
import csv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the parent directory to sys.path so we can import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models.subject import Subject
from app.models.department import Department

def extract_it_subjects():
    # Connect to the local SQLite database
    engine = create_engine('sqlite:///attendance.db')
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # Query IT department
        it_dept = db.query(Department).filter(Department.code == 'IT').first()
        
        if not it_dept:
            print("IT department not found in the database.")
            return

        # Query all subjects in IT department
        subjects = db.query(Subject).filter(Subject.department_id == it_dept.id).all()
        
        # Prepare CSV data
        csv_filename = "it_subjects.csv"
        csv_filepath = os.path.join(os.path.dirname(__file__), '..', csv_filename)
        
        with open(csv_filepath, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            # Write header exactly matching template
            writer.writerow([
                'subject_code', 'subject_name', 'subject_title', 
                'department', 'academic_year', 'semester', 
                'subject_type', 'credits', 'description', 'status'
            ])
            
            # Write rows
            for subj in subjects:
                writer.writerow([
                    subj.subject_code,
                    subj.subject_name,
                    subj.subject_title or "",
                    it_dept.code,
                    subj.academic_year,
                    subj.semester,
                    subj.subject_type,
                    subj.credits if subj.credits is not None else "",
                    subj.description or "",
                    subj.status
                ])
                
        print(f"Successfully exported {len(subjects)} IT subject(s) to {csv_filepath}")
        
    finally:
        db.close()

if __name__ == "__main__":
    extract_it_subjects()
