"""Job Hunt Tracker — сервис для ведения откликов на вакансии.

Каркас основан на учебном примере занятия 4 (FastAPI вместе).
"""

import logging
import os
import time
from datetime import date, timedelta
from enum import StrEnum

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

APP_NAME = "Job Hunt Tracker"
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("job_hunt_tracker")


def read_int_env(name: str, default: int) -> int:
    """Читает целое число из переменной окружения; при ошибке берёт значение по умолчанию."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer, using default %d", name, raw, default)
        return default


# Через сколько дней после отклика пора писать follow-up
FOLLOW_UP_DAYS = read_int_env("FOLLOW_UP_DAYS", 7)


# --- Справочники: FastAPI сам вернёт 422 на значение не из списка ---

class Source(StrEnum):
    LINKEDIN = "LinkedIn"
    HH = "hh.ru"
    COMPANY_WEBSITE = "Company website"
    REFERRAL = "Referral"
    TELEGRAM = "Telegram"
    OTHER = "Other"


class Industry(StrEnum):
    AI = "AI"
    HEALTHTECH = "Healthtech"
    FINTECH = "Fintech"
    EDTECH = "Edtech"
    ECOMMERCE = "E-commerce"
    TRAVEL = "Travel"
    GAMING = "Gaming"
    OTHER = "Other"


class Grade(StrEnum):
    MIDDLE = "Middle"
    SENIOR = "Senior"
    LEAD = "Lead"
    OTHER = "Other"


class WorkFormat(StrEnum):
    REMOTE = "Remote"
    HYBRID = "Hybrid"
    ONSITE = "Onsite"


class Priority(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Status(StrEnum):
    FOUND = "Found"
    SHORTLISTED = "Shortlisted"
    MATERIALS_READY = "Materials ready"
    APPLIED = "Applied"
    FOLLOW_UP_SENT = "Follow-up sent"
    INTERVIEW = "Interview"
    OFFER = "Offer"
    REJECTED = "Rejected"
    WITHDRAWN = "Withdrawn"


class Currency(StrEnum):
    EUR = "EUR"
    USD = "USD"
    RUB = "RUB"


CLOSED_STATUSES = {Status.REJECTED, Status.WITHDRAWN}

# Статус -> (следующий шаг, через сколько дней напомнить); None — без даты
NEXT_STEPS = {
    Status.FOUND: ("Decide whether to prepare materials", 3),
    Status.SHORTLISTED: ("Decide whether to prepare materials", 3),
    Status.MATERIALS_READY: ("Review materials and decide whether to apply", 2),
    Status.APPLIED: ("Send a follow-up if there is no answer", FOLLOW_UP_DAYS),
    Status.FOLLOW_UP_SENT: ("Send a second follow-up or close", 7),
    Status.INTERVIEW: ("Send a thank-you note and prepare for the next stage", 1),
    Status.OFFER: ("Make a decision on the offer", None),
    Status.REJECTED: ("Closed, no action needed", 0),
    Status.WITHDRAWN: ("Closed, no action needed", 0),
}


def plan_next_step(status: Status, changed_on: date, date_applied: date | None) -> tuple[str, date | None]:
    """Возвращает следующий шаг и дату напоминания для статуса."""
    action, days = NEXT_STEPS[status]
    if days is None:
        return action, None
    # Для Applied отсчёт идёт от даты отклика, для остальных — от смены статуса
    base = date_applied if status == Status.APPLIED and date_applied else changed_on
    return action, base + timedelta(days=days)


# --- Модели данных ---

class ApplicationCreate(BaseModel):
    """Поля, которые вводит пользователь."""

    company: str = Field(min_length=1, examples=["Acme Corp"])
    role: str = Field(min_length=1, examples=["ML Engineer"])
    link: str = Field(min_length=1, examples=["https://example.com/jobs/ml-engineer"])
    source: Source = Source.OTHER
    industry: Industry = Industry.OTHER
    grade: Grade = Grade.OTHER
    work_format: WorkFormat | None = None
    priority: Priority = Priority.MEDIUM
    status: Status = Status.FOUND
    date_applied: date | None = None
    # Вилка из вакансии (не ожидания кандидата)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: Currency | None = None

    @model_validator(mode="after")
    def check_salary_range(self):
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("salary_min must not be greater than salary_max")
        return self


class StatusChange(BaseModel):
    status: Status
    changed_on: date


class StatusUpdate(BaseModel):
    status: Status


class Application(ApplicationCreate):
    """Отклик целиком: поля пользователя + поля, которые заполняет сервис."""

    id: str
    next_action: str
    follow_up_date: date | None
    status_history: list[StatusChange]
    match_score: int | None = None


# --- Хранилище: словарь в памяти процесса, после перезапуска данные сбрасываются ---

applications: dict[str, Application] = {}


def add_application(
    data: ApplicationCreate,
    history: list[StatusChange] | None = None,
    match_score: int | None = None,
) -> Application:
    """Создаёт отклик: выдаёт id, считает следующий шаг, начинает историю статусов."""
    today = date.today()
    history = history or [StatusChange(status=data.status, changed_on=today)]
    fields = data.model_dump()
    if data.status == Status.APPLIED and data.date_applied is None:
        fields["date_applied"] = today
    next_action, follow_up_date = plan_next_step(data.status, history[-1].changed_on, fields["date_applied"])
    application = Application(
        **fields,
        id=f"A-{len(applications) + 1:04d}",
        next_action=next_action,
        follow_up_date=follow_up_date,
        status_history=history,
        match_score=match_score,
    )
    applications[application.id] = application
    return application


def days_ago(days: int) -> date:
    return date.today() - timedelta(days=days)


def load_demo_data() -> None:
    """Заполняет хранилище выдуманными откликами, чтобы было что смотреть сразу после запуска."""
    applications.clear()
    demo = [
        # (поля отклика, история статусов: (статус, сколько дней назад), match_score)
        (
            dict(company="Acme Corp", role="ML Engineer", link="https://example.com/jobs/acme-ml-engineer",
                 source=Source.LINKEDIN, industry=Industry.AI, grade=Grade.MIDDLE, work_format=WorkFormat.REMOTE,
                 priority=Priority.HIGH, salary_min=4000, salary_max=5500, salary_currency=Currency.EUR),
            [(Status.FOUND, 20), (Status.APPLIED, 18), (Status.INTERVIEW, 1)],
            82,
        ),
        (
            dict(company="Globex", role="Data Scientist", link="https://example.com/jobs/globex-data-scientist",
                 source=Source.HH, industry=Industry.FINTECH, grade=Grade.SENIOR, work_format=WorkFormat.HYBRID,
                 priority=Priority.MEDIUM, salary_min=300000, salary_max=400000, salary_currency=Currency.RUB),
            [(Status.FOUND, 15), (Status.APPLIED, 12)],
            64,
        ),
        (
            dict(company="Initech", role="AI Product Analyst", link="https://example.com/jobs/initech-ai-analyst",
                 source=Source.COMPANY_WEBSITE, industry=Industry.EDTECH, grade=Grade.MIDDLE,
                 work_format=WorkFormat.REMOTE, priority=Priority.MEDIUM),
            [(Status.FOUND, 3), (Status.SHORTLISTED, 2)],
            None,
        ),
        (
            dict(company="Northwind Health", role="NLP Engineer", link="https://example.com/jobs/northwind-nlp",
                 source=Source.REFERRAL, industry=Industry.HEALTHTECH, grade=Grade.SENIOR,
                 work_format=WorkFormat.ONSITE, priority=Priority.HIGH,
                 salary_min=6000, salary_max=7500, salary_currency=Currency.USD),
            [(Status.FOUND, 30), (Status.APPLIED, 28), (Status.FOLLOW_UP_SENT, 20), (Status.REJECTED, 10)],
            45,
        ),
        (
            dict(company="Contoso Travel", role="Python Developer", link="https://example.com/jobs/contoso-python",
                 source=Source.TELEGRAM, industry=Industry.TRAVEL, grade=Grade.MIDDLE,
                 work_format=WorkFormat.HYBRID, priority=Priority.LOW),
            [(Status.FOUND, 1)],
            None,
        ),
        (
            dict(company="Fabrikam Games", role="ML Engineer, Recommendations",
                 link="https://example.com/jobs/fabrikam-recsys", source=Source.LINKEDIN, industry=Industry.GAMING,
                 grade=Grade.LEAD, work_format=WorkFormat.REMOTE, priority=Priority.MEDIUM,
                 salary_min=6000, salary_max=8000, salary_currency=Currency.EUR),
            [(Status.FOUND, 40), (Status.APPLIED, 35), (Status.INTERVIEW, 25), (Status.OFFER, 3)],
            77,
        ),
    ]
    for fields, steps, match_score in demo:
        history = [StatusChange(status=status, changed_on=days_ago(days)) for status, days in steps]
        applied_on = next((h.changed_on for h in history if h.status == Status.APPLIED), None)
        data = ApplicationCreate(**fields, status=history[-1].status, date_applied=applied_on)
        add_application(data, history, match_score)
    logger.info("Loaded %d demo applications", len(applications))


def find_application(application_id: str) -> Application:
    application = applications.get(application_id)
    if application is None:
        logger.warning("Application %s not found", application_id)
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    return application


def find_duplicate(data: ApplicationCreate) -> Application | None:
    """Дубль — та же ссылка или та же пара «компания + роль» (без учёта регистра и пробелов)."""
    key = (data.company.strip().lower(), data.role.strip().lower())
    for application in applications.values():
        if application.link == data.link or (application.company.strip().lower(), application.role.strip().lower()) == key:
            return application
    return None


# --- Приложение и маршруты ---

app = FastAPI(title=APP_NAME, version=APP_VERSION)

logger.info("Starting %s, version %s, FOLLOW_UP_DAYS=%d", APP_NAME, APP_VERSION, FOLLOW_UP_DAYS)
load_demo_data()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Пишет в лог каждый запрос: метод, путь, код ответа и время обработки."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    logger.info("%s %s -> %d (%.1f ms)", request.method, target, response.status_code, elapsed_ms)
    return response


@app.get("/")
def root():
    return {"message": f"{APP_NAME} is running. Open /docs for the API."}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"app": APP_NAME, "version": APP_VERSION}


@app.get("/applications")
def list_applications(status: Status | None = None) -> list[Application]:
    """Все отклики или только с указанным статусом."""
    return [a for a in applications.values() if status is None or a.status == status]


@app.get("/applications/{application_id}")
def get_application(application_id: str) -> Application:
    return find_application(application_id)


@app.post("/applications", status_code=201)
def create_application(data: ApplicationCreate) -> Application:
    """Добавляет отклик; повторная вакансия — 409."""
    duplicate = find_duplicate(data)
    if duplicate is not None:
        logger.warning("Duplicate application rejected: %s, %s (already %s)", data.company, data.role, duplicate.id)
        raise HTTPException(status_code=409, detail=f"Application already exists: {duplicate.id}")
    application = add_application(data)
    logger.info("Created application %s: %s, %s [%s]", application.id, application.company, application.role,
                application.status)
    return application


@app.patch("/applications/{application_id}/status")
def update_status(application_id: str, update: StatusUpdate) -> Application:
    """Меняет статус: пишет его в историю и пересчитывает следующий шаг."""
    application = find_application(application_id)
    if update.status == application.status:
        return application
    today = date.today()
    old_status = application.status
    application.status = update.status
    application.status_history.append(StatusChange(status=update.status, changed_on=today))
    if update.status == Status.APPLIED and application.date_applied is None:
        application.date_applied = today
    application.next_action, application.follow_up_date = plan_next_step(
        update.status, today, application.date_applied
    )
    logger.info("Application %s status: %s -> %s", application.id, old_status, update.status)
    return application
