import sys
import os
import io

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from app.main import app
from app.database.database import Base, engine, SessionLocal
from app.models.student import Student

client = TestClient(app)


def run_tests():
    print("========================================")
    print("STARTING BACKEND API VERIFICATION TESTS")
    print("========================================")

    # 1. Health check
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("[PASS] 1. Health Check OK:", res.json())

    # 2. Database reset & setup
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("[PASS] 2. Database Schema Created")

    # 3. Seed test students
    import scripts.seed as seeder
    seeder.seed()
    print("[PASS] 3. Database Seeded Successfully (Realistic Roll Numbers & Cohorts)")

    # 4. Get Student Statistics
    res = client.get("/api/v1/students/stats")
    assert res.status_code == 200, f"Stats failed: {res.text}"
    stats = res.json()
    assert stats["total_students"] >= 14
    assert stats["active_students"] >= 13
    assert stats["departments"] >= 4
    print("[PASS] 4. GET /api/v1/students/stats OK:", stats)

    # 5. Get Paginated Students
    res = client.get("/api/v1/students?page=1&limit=5")
    assert res.status_code == 200, f"Get students failed: {res.text}"
    data = res.json()
    assert len(data["items"]) == 5
    assert data["total"] >= 14
    assert data["total_pages"] >= 3
    print(f"[PASS] 5. GET /api/v1/students (page 1, limit 5) OK - Total: {data['total']}")

    # 6. Search Students by Roll Number (e.g. 2023PECAIDS230)
    res = client.get("/api/v1/students?search=2023PECAIDS230")
    assert res.status_code == 200
    search_data = res.json()
    assert len(search_data["items"]) == 1
    assert search_data["items"][0]["name"] == "Divya Krishnan"
    print("[PASS] 6. Search by roll_no '2023PECAIDS230' OK")

    # 7. Multi-filter students (department=Information Technology, semester=5, section=A)
    res = client.get("/api/v1/students?department=Information+Technology&semester=5&section=A")
    assert res.status_code == 200
    filter_data = res.json()
    assert len(filter_data["items"]) >= 2
    print(f"[PASS] 7. Filter by Dept + Sem + Sec OK: {len(filter_data['items'])} students found")

    # 8. Create Student with flexible roll_no (POST /api/v1/students)
    new_student = {
        "roll_no": "2023PECCSE199",
        "name": "Test Student Automated",
        "email": "test.cse199@example.com",
        "phone": "+91 9999988888",
        "department": "Computer Science",
        "semester": 3,
        "section": "Z",
        "academic_year": "2023-2027",
        "status": "active",
    }
    res = client.post("/api/v1/students", json=new_student)
    assert res.status_code == 201, f"Create student failed: {res.text}"
    created_id = res.json()["id"]
    print("[PASS] 8. POST /api/v1/students Created Flexible Roll No ID:", created_id)

    # 9. Duplicate Roll Number Rejection
    res = client.post("/api/v1/students", json=new_student)
    assert res.status_code == 409, f"Expected 409 Conflict, got {res.status_code}: {res.text}"
    print("[PASS] 9. Duplicate roll_no rejected with 409 Conflict:", res.json())

    # 10. Update Student (PUT /api/v1/students/{id})
    update_payload = {"name": "Test Student Updated", "section": "AIML-B"}
    res = client.put(f"/api/v1/students/{created_id}", json=update_payload)
    assert res.status_code == 200, f"Update failed: {res.text}"
    assert res.json()["name"] == "Test Student Updated"
    assert res.json()["section"] == "AIML-B"
    print("[PASS] 10. PUT /api/v1/students/{id} Updated OK")

    # 11. Delete Single Student (DELETE /api/v1/students/{id})
    res = client.delete(f"/api/v1/students/{created_id}")
    assert res.status_code == 200, f"Delete failed: {res.text}"
    # Verify 404 on get
    res_after = client.get(f"/api/v1/students/{created_id}")
    assert res_after.status_code == 404
    print("[PASS] 11. DELETE /api/v1/students/{id} Deleted and verified 404")

    # 12. Bulk Delete API (POST /api/v1/students/bulk-delete)
    s1_res = client.post("/api/v1/students", json={
        "roll_no": "2023PECDEL01",
        "name": "Delete Target 1",
        "email": "del1@example.com",
        "phone": "+91 9999911111",
        "department": "Computer Science",
        "semester": 1,
        "section": "A",
        "academic_year": "2024-2028",
        "status": "active",
    })
    s2_res = client.post("/api/v1/students", json={
        "roll_no": "2023PECDEL02",
        "name": "Delete Target 2",
        "email": "del2@example.com",
        "phone": "+91 9999922222",
        "department": "Computer Science",
        "semester": 1,
        "section": "A",
        "academic_year": "2024-2028",
        "status": "active",
    })
    del_ids = [s1_res.json()["id"], s2_res.json()["id"]]
    bulk_del_res = client.post("/api/v1/students/bulk-delete", json={"student_ids": del_ids})
    assert bulk_del_res.status_code == 200, f"Bulk delete failed: {bulk_del_res.text}"
    assert bulk_del_res.json()["deleted_count"] == 2
    print(f"[PASS] 12. POST /api/v1/students/bulk-delete OK: Deleted {bulk_del_res.json()['deleted_count']} students")

    # 13. CSV Template Download
    res = client.get("/api/v1/students/import-template")
    assert res.status_code == 200
    assert "roll_no,name,email" in res.text
    print("[PASS] 13. GET /api/v1/students/import-template OK")

    # 14. Bulk Import CSV with Valid + Invalid Rows
    csv_content = (
        "roll_no,name,email,phone,department,semester,section,academic_year,status\n"
        "2023PECCSE991,Bulk CSE,bulkcse991@example.com,9876543290,Computer Science,5,A,2023-2027,active\n"
        "2023PECAIDS992,Bulk AIDS,bulkaids992@example.com,9876543291,Artificial Intelligence & Data Science,3,Z,2024-2028,active\n"
        ",No Roll Student,noroll@example.com,9876543292,Information Technology,5,A,2023-2027,active\n"
        "2023PECIT993,Invalid Sem Student,badsem@example.com,9876543293,Information Technology,15,A,2023-2027,active\n"
        "2023PECCSE991,Duplicate In Batch,dup@example.com,9876543294,Computer Science,5,A,2023-2027,active\n"
    )
    files = {"file": ("students_import.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/students/import", files=files)
    assert res.status_code == 200, f"Bulk import failed: {res.text}"
    import_res = res.json()
    assert import_res["total_rows"] == 5
    assert import_res["successful"] == 2
    assert import_res["failed"] == 3
    assert len(import_res["errors"]) == 3
    print(f"[PASS] 14. POST /api/v1/students/import OK: {import_res['successful']} imported, {import_res['failed']} errors reported.")

    print("========================================")
    print("ALL 14 BACKEND API TESTS PASSED PERFECTLY!")
    print("========================================")


if __name__ == "__main__":
    run_tests()
