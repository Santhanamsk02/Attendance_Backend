import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, func
from app.database.database import Base


class Admin(Base):
    __tablename__ = "admins"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password = Column(
        String(255),
        nullable=False,
    )
    name = Column(
        String(150),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self):
        return f"<Admin {self.email} - {self.name}>"
