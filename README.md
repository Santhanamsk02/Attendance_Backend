<div align="center">
  <img src="https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png" alt="FastAPI" width="300"/>

  # 🎓 Student Attendance Management System API

  **A Premium, High-Performance, and Scalable RESTful Backend Architecture**

  <p align="center">
    <a href="#"><img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
    <a href="#"><img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"></a>
    <a href="#"><img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"></a>
    <a href="#"><img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy"></a>
    <a href="#"><img src="https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase"></a>
  </p>

  <p align="center">
    <a href="#"><img src="https://img.shields.io/github/stars/yourusername/attendance-backend?style=flat-square&color=blue" alt="Stars"></a>
    <a href="#"><img src="https://img.shields.io/github/license/yourusername/attendance-backend?style=flat-square&color=green" alt="License"></a>
    <a href="#"><img src="https://img.shields.io/badge/build-passing-brightgreen?style=flat-square" alt="Build"></a>
  </p>

  <i>Engineered for reliability. Designed for scale. Built for the modern educational institution.</i>
</div>

---

## 🌟 Project Overview

The **Student Attendance Management System API** solves the complex logistical challenges of tracking student attendance across dynamic academic structures. Traditional systems struggle with edge cases like dynamic section assignments, complex timetable routing, and sudden calendar overrides (holidays, day swaps). 

This backend was built to handle these challenges elegantly. By leveraging asynchronous request handling, stateless security, and a strictly normalized relational database, this API provides an unbreakable foundation for web and mobile clients. 

**Core Business Value:**
- Eliminates manual attendance tracking errors.
- Delivers real-time analytics for administrative oversight.
- Supports complex, multi-tiered institutional hierarchies (Departments → Batches → Semesters → Sections).

---

## ✨ Key Features

| Feature | Description | Technology |
| :--- | :--- | :--- |
| 🔐 **Stateless Security** | Robust JWT-based authentication with bcrypt password hashing. | `python-jose`, `passlib` |
| 👥 **Granular RBAC** | Strict Role-Based Access Control isolating Admin and Faculty layers. | `FastAPI Dependencies` |
| 📅 **Dynamic Timetabling** | Complex routing for varying weekly schedules and semester structures. | `SQLAlchemy ORM` |
| 🔄 **Calendar Overrides** | System intelligently handles holidays and day-swaps for attendance logic. | `PostgreSQL` |
| 📊 **Real-time Analytics** | Aggregated data streams for dashboards and reporting. | `SQLAlchemy Async` |
| 🛡️ **Schema Migrations** | Fully version-controlled database schema changes. | `Alembic` |
| ⚡ **High Performance** | Asynchronous endpoint execution for maximum throughput. | `Uvicorn` |

---

## 🏗 System Architecture

```mermaid
graph TD
    Client[Client Applications<br>Web / Flutter App] -->|HTTP/REST| AG[FastAPI Router<br>Endpoint Layer]
    
    subgraph Backend [FastAPI Application]
        AG --> Auth[Authentication Middleware<br>JWT Security]
        Auth --> Controllers[Controllers<br>Business Logic]
        Controllers --> ORM[SQLAlchemy ORM<br>Data Access Layer]
    end
    
    ORM -->|TCP/IP| DB[(PostgreSQL Database<br>Supabase)]
    
    classDef client fill:#f9f,stroke:#333,stroke-width:2px;
    classDef backend fill:#bbf,stroke:#333,stroke-width:2px;
    classDef db fill:#ff9,stroke:#333,stroke-width:2px;
    
    class Client client;
    class Backend backend;
    class DB db;
```

---

## 🔄 Request Lifecycle

```mermaid
sequenceDiagram
    participant U as Client (App/Web)
    participant R as FastAPI Router
    participant M as Auth Dependency
    participant C as Controller Logic
    participant DB as PostgreSQL (Supabase)

    U->>R: GET /api/v1/students
    R->>M: Validate JWT Token
    
    alt Token Invalid
        M-->>U: 401 Unauthorized
    else Token Valid
        M->>C: Proceed with User Context
        C->>DB: Query Database via SQLAlchemy
        DB-->>C: Return Entity Data
        C->>C: Serialize via Pydantic
        C-->>U: 200 OK (JSON Response)
    end
```

---

## 🧠 Backend Architecture Pattern

This project adheres to a modern **Controller-Service-Repository** inspired pattern, adapted for FastAPI's dependency injection system.

| Layer | Responsibility | Technology |
| :--- | :--- | :--- |
| **Router** | Maps HTTP methods to Python functions, validates incoming request payloads. | `FastAPI`, `Pydantic` |
| **Dependency** | Handles cross-cutting concerns like Auth, DB Sessions, and RBAC. | `FastAPI Depends` |
| **Controller** | Executes core business logic and error handling. | `Python` |
| **Model** | Defines the database schema and object relationships. | `SQLAlchemy` |

---

## 🛠 Technology Stack

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![PostgreSQL](https://img.shields.io/badge/postgresql-4169e1?style=for-the-badge&logo=postgresql&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![JWT](https://img.shields.io/badge/JWT-black?style=for-the-badge&logo=JSON%20web%20tokens)

<details>
<summary><b>Click to see detailed technology choices</b></summary>

- **FastAPI**: Chosen for its incredible performance, automatic interactive API documentation (Swagger/ReDoc), and native support for asynchronous programming.
- **SQLAlchemy**: The industry standard for Python ORMs. Allows for complex, deeply relational queries while keeping Pythonic syntax.
- **Supabase**: Provides a scalable, managed PostgreSQL database with built-in connection pooling (`PgBouncer`) required for serverless edge deployments.
- **Alembic**: Critical for managing schema changes over time without data loss.
- **Pydantic**: Enforces strict data validation on all incoming and outgoing requests.
</details>

---

## 📁 Project Structure

```text
backend/
├── alembic/                # Database migration environment
│   └── versions/           # Version-controlled schema scripts
├── app/
│   ├── core/               # App configuration, security, and hashing
│   ├── database/           # SQLAlchemy engine & DB session setup
│   ├── models/             # SQLAlchemy ORM Models (DB Entities)
│   ├── routers/            # API Route definitions
│   ├── schemas/            # Pydantic Schemas (Serialization)
│   └── main.py             # Application Entry Point
├── scripts/                # Utilities (seed.py, reset_db.py)
├── .env                    # Environment Secrets (Not in VCS)
├── alembic.ini             # Migration Config
└── requirements.txt        # Dependencies
```

---

## 🗄 Database Architecture

```mermaid
erDiagram
    USERS ||--o| ADMINS : "is"
    USERS ||--o| TEACHERS : "is"
    
    DEPARTMENTS ||--o{ SUBJECTS : "owns"
    DEPARTMENTS ||--o{ STUDENTS : "enrolls"
    
    BATCHES ||--o{ STUDENTS : "groups"
    
    TEACHERS ||--o{ TEACHER_ASSIGNMENTS : "teaches"
    SUBJECTS ||--o{ TEACHER_ASSIGNMENTS : "has"
    
    TEACHER_ASSIGNMENTS ||--o{ ATTENDANCE_SESSIONS : "generates"
    
    ATTENDANCE_SESSIONS ||--o{ ATTENDANCE_MARKS : "contains"
    STUDENTS ||--o{ ATTENDANCE_MARKS : "receives"
```

### Core Entities
- **Users**: Base authentication table handling credentials.
- **Students / Teachers / Admins**: Profile tables linked to User accounts.
- **TeacherAssignments**: Resolves the Many-to-Many relationship mapping a Teacher to a Subject, Section, and specific Timetable period.
- **AttendanceSessions**: A distinct log of a class taking place.
- **AttendanceMarks**: The granular record (Present/Absent) of a single student for a specific session.

---

## 🔐 Security Architecture

Security is handled via **stateless JWT tokens**. 

1. Client POSTs credentials to `/api/v1/auth/login`.
2. Server verifies against bcrypt-hashed password in DB.
3. Server signs and issues a JWT token.
4. Client passes token in the `Authorization: Bearer <token>` header for all subsequent requests.
5. FastAPI Dependencies inject the current `User` object into the request context, enforcing RBAC based on the user's role.

---

## 🌐 API Documentation

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :---: |
| `POST` | `/api/v1/auth/login` | Authenticate user & get JWT | ❌ |
| `GET` | `/api/v1/teachers/profile` | Get current teacher profile | ✅ (Teacher) |
| `GET` | `/api/v1/students` | List all students (paginated) | ✅ (Admin) |
| `POST` | `/api/v1/attendance/mark` | Submit attendance records | ✅ (Teacher) |
| `GET` | `/api/v1/admin/reports` | Get institutional analytics | ✅ (Admin) |

*(Full interactive documentation available at `/docs` when the server is running).*

---

## 📥 API Request Example

**POST `/api/v1/auth/login`**

*Request:*
```json
{
  "username": "admin@example.com",
  "password": "securepassword123"
}
```

*Response (200 OK):*
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5c...",
  "token_type": "bearer",
  "user": {
    "id": "uuid-1234",
    "email": "admin@example.com",
    "role": "admin"
  }
}
```

---

## ⚡ Getting Started

### 1. Clone & Environment
```bash
git clone https://github.com/yourusername/attendance-backend.git
cd attendance-backend

python -m venv venv
venv\Scripts\activate   # Windows
source venv/bin/activate # Mac/Linux

pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Create a `.env` file in the root folder:
```env
# Database Connection (Supabase Pooler Example)
DATABASE_URL=postgresql://postgres.projectref:password@aws-0-region.pooler.supabase.com:6543/postgres

# API Settings
PROJECT_NAME="Attendance API"
API_V1_STR=/api/v1
CORS_ORIGINS=["*"]
```

### 3. Initialize Database
```bash
alembic upgrade head
python scripts/seed.py
```

### 4. Run Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🛡 Error Handling

The API employs a global exception handler. All failed validations and business logic errors return a strictly typed JSON structure.

*Example 422 Unprocessable Entity:*
```json
{
  "detail": "Validation error",
  "errors": [
    "body -> email: value is not a valid email address",
    "body -> password: field required"
  ]
}
```

---

## 🚀 Deployment Architecture

```mermaid
graph LR
    Dev[Developer] -->|Git Push| GitHub[GitHub Repo]
    GitHub -->|Trigger| Render[Cloud Platform<br>e.g. Render / Heroku]
    Render -->|Build| Uvicorn[Uvicorn Workers]
    Uvicorn -->|Connection Pooler| Supabase[(Supabase<br>PostgreSQL)]
```

The application is fully stateless and can be horizontally scaled across multiple Uvicorn workers behind a reverse proxy (like Nginx) or deployed natively to modern PaaS providers.

---

## 🔮 Future Improvements

- [x] JWT Authentication & RBAC
- [x] Complex Timetabling Schema
- [x] Calendar Override Logic
- [ ] Redis caching for high-traffic analytics endpoints
- [ ] Dockerization (`Dockerfile` and `docker-compose.yml`)
- [ ] Automated CI/CD pipeline using GitHub Actions
- [ ] Websocket support for real-time dashboard updates

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---
<div align="center">
  <i>Developed with precision for modern educational architecture.</i>
</div>
