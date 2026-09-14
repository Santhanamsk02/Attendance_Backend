from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.routers import students, teachers, subjects, auth, teacher_access, teacher, attendance, timetable, admin_attendance, admin_institution, section_assignments, calendar_overrides, admin_reports

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Backend REST API for Student Attendance Management System (Day 1)",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global validation error handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        field = " -> ".join([str(loc) for loc in err.get("loc", [])])
        msg = err.get("msg", "Invalid value")
        errors.append(f"{field}: {msg}")
    
    print(f"!!! VALIDATION ERROR on {request.url} !!!")
    print(f"Errors: {errors}")
    try:
        body = await request.body()
        print(f"Body: {body.decode()}")
    except:
        pass
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": errors,
        },
    )


# Generic catch-all exception handler to prevent stack trace leaks
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    with open("server_error.log", "a") as f:
        f.write(f"Error on {request.url}:\n")
        traceback.print_exc(file=f)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected internal server error occurred. Please try again later."
        },
    )


# Health checks
@app.get("/health", tags=["Health"])
@app.get(f"{settings.API_V1_STR}/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "service": settings.PROJECT_NAME, "version": "1.0.0"}


# Include Routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(teacher_access.router, prefix=settings.API_V1_STR)
app.include_router(teacher.router, prefix=settings.API_V1_STR)
app.include_router(attendance.router, prefix=settings.API_V1_STR)
app.include_router(students.router, prefix=settings.API_V1_STR)
app.include_router(teachers.router, prefix=settings.API_V1_STR)
app.include_router(subjects.router, prefix=settings.API_V1_STR)
app.include_router(timetable.router, prefix=settings.API_V1_STR)
app.include_router(admin_attendance.router, prefix=settings.API_V1_STR)
app.include_router(admin_institution.router, prefix=settings.API_V1_STR)
app.include_router(section_assignments.router, prefix=settings.API_V1_STR)
app.include_router(calendar_overrides.router, prefix=settings.API_V1_STR)

from app.routers import admin_attendance_dashboard
app.include_router(admin_attendance_dashboard.router, prefix=settings.API_V1_STR)
app.include_router(admin_reports.router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
