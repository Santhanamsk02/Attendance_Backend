import sys
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Add the parent directory to sys.path so we can import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()
postgres_url = os.getenv("DATABASE_URL")
if not postgres_url:
    print("DATABASE_URL not found in .env")
    sys.exit(1)

from app.database.database import Base
from app.models import *

def create_tables():
    engine = create_engine(postgres_url)
    print("Creating all missing tables...")
    Base.metadata.create_all(engine)
    print("Tables created successfully!")

if __name__ == "__main__":
    create_tables()
