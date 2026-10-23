"""Тесты Job Hunt Tracker. Запуск: python -m pytest -v"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app_final

client = TestClient(app_final.app)

NEW_APPLICATION = {
    "company": "Tailspin Toys",
    "role": "Data Engineer",
    "link": "https://example.com/jobs/tailspin-data",
    "source": "LinkedIn",
    "industry": "E-commerce",
}


@pytest.fixture(autouse=True)
def fresh_data():
    """Перед каждым тестом возвращаем демо-данные, чтобы тесты не влияли друг на друга."""
    app_final.load_demo_data()


# --- Служебные маршруты ---

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_app_version():
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"app": "Job Hunt Tracker", "version": app_final.APP_VERSION}


def test_root_points_to_docs():
    response = client.get("/")
    assert response.status_code == 200
    assert "/docs" in response.json()["message"]


# --- Отклики ---

def test_list_applications_returns_demo_data():
    response = client.get("/applications")
    assert response.status_code == 200
    assert len(response.json()) == 6


def test_filter_applications_by_status():
    response = client.get("/applications", params={"status": "Applied"})
    assert response.status_code == 200
    assert [a["company"] for a in response.json()] == ["Globex"]


def test_unknown_status_filter_returns_422():
    response = client.get("/applications", params={"status": "Hired"})
    assert response.status_code == 422


def test_get_application_by_id():
    response = client.get("/applications/A-0001")
    assert response.status_code == 200
    assert response.json()["company"] == "Acme Corp"


def test_get_unknown_application_returns_404():
    response = client.get("/applications/A-9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Application A-9999 not found"


def test_create_application_fills_service_fields():
    response = client.post("/applications", json=NEW_APPLICATION)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "A-0007"
    assert body["status"] == "Found"
    assert body["follow_up_date"] == str(date.today() + timedelta(days=3))
    assert body["status_history"] == [{"status": "Found", "changed_on": str(date.today())}]


def test_duplicate_application_returns_409():
    duplicate = {"company": " acme corp ", "role": "ml engineer", "link": "https://example.com/other"}
    response = client.post("/applications", json=duplicate)
    assert response.status_code == 409
    assert response.json()["detail"] == "Application already exists: A-0001"


def test_invalid_salary_range_returns_422():
    response = client.post("/applications", json={**NEW_APPLICATION, "salary_min": 5000, "salary_max": 4000})
    assert response.status_code == 422


def test_status_change_updates_history_and_follow_up():
    application_id = client.post("/applications", json=NEW_APPLICATION).json()["id"]
    response = client.patch(f"/applications/{application_id}/status", json={"status": "Applied"})
    assert response.status_code == 200
    body = response.json()
    today = date.today()
    assert body["date_applied"] == str(today)
    assert body["follow_up_date"] == str(today + timedelta(days=app_final.FOLLOW_UP_DAYS))
    assert [h["status"] for h in body["status_history"]] == ["Found", "Applied"]


def test_status_change_for_unknown_application_returns_404():
    response = client.patch("/applications/A-9999/status", json={"status": "Applied"})
    assert response.status_code == 404


# --- Напоминания и аналитика ---

def test_follow_ups_lists_overdue_open_applications():
    response = client.get("/follow-ups")
    assert response.status_code == 200
    due = {item["company"]: item["days_overdue"] for item in response.json()}
    assert due == {"Globex": 5, "Acme Corp": 0}


def test_follow_ups_days_ahead_out_of_range_returns_422():
    response = client.get("/follow-ups", params={"days_ahead": 99})
    assert response.status_code == 422


def test_stats_funnel():
    response = client.get("/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["total"] == 6
    assert stats["applied"] == 4
    assert stats["interviews"] == 2
    assert stats["interview_rate"] == 50.0
    assert stats["offers"] == 1


def test_stats_group_by_source():
    response = client.get("/stats", params={"group_by": "source"})
    assert response.status_code == 200
    assert response.json()["groups"]["LinkedIn"] == {"total": 2, "applied": 2, "interviews": 2, "interview_rate": 100.0}


def test_stats_unknown_group_by_returns_400():
    response = client.get("/stats", params={"group_by": "salary"})
    assert response.status_code == 400


# --- Сравнение вакансии с навыками ---

MATCH_REQUEST = {
    "vacancy_text": "We need a Python developer with FastAPI, SQL and Docker. Kubernetes is a plus.",
    "candidate_skills": ["Python", "SQL", "Git"],
    "resume_bullets": [
        "Organised team offsites",
        "Wrote SQL reports for the sales team",
        "Built a FastAPI service with Docker for internal analytics",
    ],
}


def test_match_returns_matched_missing_and_verdict():
    response = client.post("/match", json=MATCH_REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body["vacancy_skills"] == ["Python", "SQL", "FastAPI", "Docker", "Kubernetes"]
    assert body["missing"] == ["Kubernetes"]
    assert body["match_percent"] == 80
    assert body["verdict"] == "Apply now"


def test_match_ranks_bullets_without_changing_text():
    response = client.post("/match", json=MATCH_REQUEST)
    ranked = [bullet["text"] for bullet in response.json()["ranked_bullets"]]
    assert ranked == [
        "Built a FastAPI service with Docker for internal analytics",
        "Wrote SQL reports for the sales team",
        "Organised team offsites",
    ]
    assert sorted(ranked) == sorted(MATCH_REQUEST["resume_bullets"])


def test_find_skills_matches_whole_words_only():
    assert app_final.find_skills("JavaScript and GitHub Actions") == ["JavaScript", "CI/CD"]


def test_match_without_known_skills_returns_400():
    response = client.post("/match", json={"vacancy_text": "Friendly team and good coffee"})
    assert response.status_code == 400


def test_match_application_saves_match_score():
    response = client.post("/applications/A-0003/match", json=MATCH_REQUEST)
    assert response.status_code == 200
    assert client.get("/applications/A-0003").json()["match_score"] == 80


# --- Настройки из окружения ---

def test_read_int_env_falls_back_on_invalid_value(monkeypatch):
    monkeypatch.setenv("FOLLOW_UP_DAYS", "abc")
    assert app_final.read_int_env("FOLLOW_UP_DAYS", 7) == 7
    monkeypatch.setenv("FOLLOW_UP_DAYS", "5")
    assert app_final.read_int_env("FOLLOW_UP_DAYS", 7) == 5
