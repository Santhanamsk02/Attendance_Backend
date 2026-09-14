import os
import sys

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database.database import engine, Base
import app.models  # Import all models

def reset_db():
    print("Dropping all existing tables...")
    Base.metadata.drop_all(bind=engine)
    print("Executing DROP TABLE alembic_version (if exists)...")
    with engine.connect() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version;"))
        conn.commit()
    print("Database reset complete.")

if __name__ == "__main__":
    import sqlalchemy as sa
    reset_db()
