"""Job Hunt Tracker — сервис для ведения откликов на вакансии.

Каркас основан на учебном примере занятия 4 (FastAPI вместе).
"""

import logging
import os

from fastapi import FastAPI

APP_NAME = "Job Hunt Tracker"
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("job_hunt_tracker")

app = FastAPI(title=APP_NAME, version=APP_VERSION)

logger.info("Starting %s, version %s", APP_NAME, APP_VERSION)


@app.get("/")
def root():
    return {"message": f"{APP_NAME} is running. Open /docs for the API."}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"app": APP_NAME, "version": APP_VERSION}
