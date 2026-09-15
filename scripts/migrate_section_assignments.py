import sys
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the parent directory to sys.path so we can import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables for Postgres URL
load_dotenv()
postgres_url = os.getenv("DATABASE_URL")
if not postgres_url:
    print("DATABASE_URL not found in .env")
    sys.exit(1)

from app.models.department import Department
from app.models.batch import Batch
from app.models.teacher import Teacher
from app.models.subject import Subject
from app.models.reference import AcademicYear
from app.models.section_assignment import SectionSubjectAssignment

def migrate():
    # Setup SQLite Session
    sqlite_engine = create_engine('sqlite:///attendance.db')
    SqliteSession = sessionmaker(bind=sqlite_engine)
    sq_db = SqliteSession()

    # Setup Postgres Session
    postgres_engine = create_engine(postgres_url)
    PgSession = sessionmaker(bind=postgres_engine)
    pg_db = PgSession()

    try:
        print("Fetching mappings...")
        
        # 1. Department Mapping
        sq_depts = sq_db.query(Department).all()
        pg_depts = pg_db.query(Department).all()
        dept_map = {}
        for sd in sq_depts:
            for pd in pg_depts:
                if sd.code == pd.code:
                    dept_map[sd.id] = pd.id
                    break
                    
        # Find IT department old and new IDs
        it_sq_id = None
        it_pg_id = None
        for d in sq_depts:
            if d.code == 'IT':
                it_sq_id = d.id
                break
        for d in pg_depts:
            if d.code == 'IT':
                it_pg_id = d.id
                break
                
        if not it_sq_id or not it_pg_id:
            print("IT department not found in one of the databases.")
            return

        # 2. Batch Mapping
        sq_batches = sq_db.query(Batch).all()
        pg_batches = pg_db.query(Batch).all()
        batch_map = {}
        for sb in sq_batches:
            for pb in pg_batches:
                if pb.department_id == dept_map.get(sb.department_id) and pb.batch_name == sb.batch_name:
                    batch_map[sb.id] = pb.id
                    break

        # 3. Teacher Mapping
        sq_teachers = sq_db.query(Teacher).all()
        pg_teachers = pg_db.query(Teacher).all()
        teacher_map = {}
        for st in sq_teachers:
            for pt in pg_teachers:
                if st.employee_id == pt.employee_id:
                    teacher_map[st.id] = pt.id
                    break

        # 4. Academic Year Mapping
        sq_years = sq_db.query(AcademicYear).all()
        
        # Insert missing years into Postgres
        for sy in sq_years:
            py = pg_db.query(AcademicYear).filter(AcademicYear.name == sy.name).first()
            if not py:
                py = AcademicYear(name=sy.name, start_date=sy.start_date, end_date=sy.end_date, is_current=sy.is_current, status=sy.status)
                pg_db.add(py)
        pg_db.commit()
        
        pg_years = pg_db.query(AcademicYear).all()
        year_map = {}
        for sy in sq_years:
            for py in pg_years:
                if sy.name == py.name:
                    year_map[sy.id] = py.id
                    break

        # 5. Subject Mapping
        sq_subjects = sq_db.query(Subject).all()
        pg_subjects = pg_db.query(Subject).all()
        subject_map = {}
        for ss in sq_subjects:
            for ps in pg_subjects:
                if ss.subject_code == ps.subject_code and ss.academic_year == ps.academic_year:
                    subject_map[ss.id] = ps.id
                    break
                    
        print("Mappings built successfully.")
        
        # Clear existing in Postgres for IT department
        pg_db.query(SectionSubjectAssignment).filter(SectionSubjectAssignment.department_id == it_pg_id).delete()
        pg_db.commit()
        
        target_sections = ['A', 'B', 'C', 'D', 'E']

        # Migrate Section Assignments
        print("Migrating SectionSubjectAssignments...")
        sq_assignments = sq_db.query(SectionSubjectAssignment).filter(
            SectionSubjectAssignment.department_id == it_sq_id,
            SectionSubjectAssignment.section_id.in_(target_sections)
        ).all()
        
        migrated_assignments = 0
        skipped_assignments = 0
        
        for sa in sq_assignments:
            # Resolve foreign keys
            new_teacher_id = teacher_map.get(sa.teacher_id)
            new_subject_id = subject_map.get(sa.subject_id)
            new_dept_id = dept_map.get(sa.department_id)
            new_batch_id = batch_map.get(sa.batch_id) if sa.batch_id else None
            new_year_id = year_map.get(sa.academic_year_id) if sa.academic_year_id else None
            
            if not new_teacher_id or not new_subject_id or (sa.academic_year_id and not new_year_id):
                skipped_assignments += 1
                if skipped_assignments <= 5:
                    print(f"Skipping assignment {sa.id}: new_teacher_id={new_teacher_id}, new_subject_id={new_subject_id}, new_year_id={new_year_id}")
                continue
                
            # Create new assignment
            pg_assignment = SectionSubjectAssignment(
                teacher_id=new_teacher_id,
                subject_id=new_subject_id,
                department_id=new_dept_id,
                batch_id=new_batch_id,
                academic_year_id=new_year_id,
                semester=sa.semester,
                section_id=sa.section_id,
            )
            pg_db.add(pg_assignment)
            migrated_assignments += 1
            
        print("Committing changes to Postgres DB...")
        pg_db.commit()
        
        print(f"Successfully migrated {migrated_assignments} SectionSubjectAssignments (Skipped: {skipped_assignments}).")

    except Exception as e:
        pg_db.rollback()
        print(f"Error during migration: {e}")
    finally:
        sq_db.close()
        pg_db.close()

if __name__ == "__main__":
    migrate()
