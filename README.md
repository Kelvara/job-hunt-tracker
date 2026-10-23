# Job Hunt Tracker

[![CI](https://github.com/Kelvara/job-hunt-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/Kelvara/job-hunt-tracker/actions/workflows/ci.yml)

Сервис на FastAPI для ведения поиска работы: хранит отклики на вакансии, ведёт их по воронке статусов (от «найдено» до оффера), подсказывает следующий шаг и напоминает о follow-up, показывает аналитику по источникам, грейдам и индустриям, а также сравнивает вакансию с навыками кандидата — процент совпадения, недостающие навыки и порядок пунктов резюме под вакансию.

**Для кого:** для человека, который ищет работу и откликается на много вакансий сразу — чтобы не терять отклики, вовремя писать follow-up и видеть, какие источники и типы вакансий дают интервью.

Каркас (`/`, `/health`, переменные окружения) основан на учебном примере `app_final.py` с занятия 4 курса «Инфраструктура и администрирование» (FastAPI).

## Возможности

| Метод и маршрут | Что делает |
|---|---|
| `GET /` | Приветствие и ссылка на `/docs` |
| `GET /health` | Проверка работоспособности → `{"status": "ok"}` |
| `GET /version` | Название и версия приложения |
| `GET /applications?status=` | Список откликов, фильтр по статусу |
| `GET /applications/{id}` | Один отклик по id (`A-0001`); нет такого → 404 |
| `POST /applications` | Добавить отклик; сервис сам выдаёт id, следующий шаг и дату follow-up; дубль (та же ссылка или компания + роль) → 409 |
| `PATCH /applications/{id}/status` | Сменить статус: запись в историю, пересчёт следующего шага |
| `GET /follow-ups?days_ahead=` | Открытые отклики, по которым пора действовать (просроченные — первыми) |
| `GET /stats` | Воронка: отклики по статусам, конверсия в интервью и оффер, зарплатные вилки по валютам, средний match_score у дошедших до интервью и у остальных |
| `GET /stats?group_by=` | Конверсия в интервью по `source`, `work_format`, `industry` или `grade`; другое поле → 400 |
| `POST /match` | Сравнение вакансии с навыками кандидата: совпавшие и недостающие навыки, процент, вердикт (Apply now / Apply after tailoring / Maybe), пункты резюме по убыванию пользы — текст пунктов не меняется |
| `POST /applications/{id}/match` | То же сравнение с сохранением процента в отклик (`match_score`) |

Статусы: Found → Shortlisted → Materials ready → Applied → Follow-up sent → Interview → Offer, а также Rejected и Withdrawn. Недопустимые значения статусов, источников и других справочников отклоняются с кодом 422.

Данные хранятся в памяти процесса: при старте загружаются 6 выдуманных демо-откликов, после перезапуска всё возвращается к ним. База данных для учебного проекта не используется.

## Окружение и установка

Нужны Python 3.12 или новее и Git. Проект проверен на Python 3.12 (GitHub Actions, Ubuntu) и Python 3.14 (macOS).

Сначала проверьте версию: `python3 --version`. Если она ниже 3.12 (например, системный Python 3.9 на macOS), установка зависимостей завершится ошибкой `No matching distribution found for fastapi`. В этом случае создайте окружение нужной версией Python явно, например `python3.12 -m venv .venv`.

```bash
git clone https://github.com/Kelvara/job-hunt-tracker.git
cd job-hunt-tracker
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

- `requirements.txt` — зависимости для работы приложения (FastAPI, Uvicorn), версии закреплены для воспроизводимости.
- `requirements-dev.txt` — то же плюс инструменты для тестов (pytest, httpx2 для тестового клиента FastAPI).

Для запуска без тестов достаточно `python -m pip install -r requirements.txt`.

## Запуск

Команда для обычной работы приложения (без `--reload`):

```bash
python -m uvicorn app_final:app --host 127.0.0.1 --port 8000
```

После запуска откройте интерактивную документацию: http://127.0.0.1:8000/docs — там можно вызвать любой маршрут кнопками **Try it out → Execute**.

`python -m uvicorn` гарантирует, что используется uvicorn из активного `.venv`, а не другой, установленный в системе.

## Тесты

```bash
python -m pytest -v
```

24 теста в `test_app.py` покрывают `/health`, `/version`, все маршруты откликов, ошибки 400 / 404 / 409 / 422, `/follow-ups`, `/stats`, `/match` и чтение настроек из окружения. Перед каждым тестом данные возвращаются к демо-набору, поэтому тесты не зависят друг от друга.

Те же тесты автоматически запускаются в GitHub Actions при каждом push и pull request (`.github/workflows/ci.yml`). После успешных тестов job `package` сохраняет artifact `job-hunt-tracker` с файлами приложения (`app_final.py`, `requirements.txt`, `.env.example`, `README.md`) на 30 дней.

## Переменные окружения

Все переменные необязательны — без них используются значения по умолчанию. Пример — в файле `.env.example`. Секретов приложение не использует; настоящий `.env` в репозиторий не попадает (он в `.gitignore`).

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `APP_VERSION` | `0.1.0` | Версия, которую возвращает `/version` |
| `FOLLOW_UP_DAYS` | `7` | Через сколько дней после отклика напоминать о follow-up |
| `APPLY_NOW_THRESHOLD` | `75` | Процент совпадения навыков, начиная с которого `/match` советует «Apply now» |
| `TAILOR_THRESHOLD` | `50` | Процент, начиная с которого вердикт — «Apply after tailoring» (ниже — «Maybe») |

Пример запуска с другими значениями:

```bash
export FOLLOW_UP_DAYS=5
export APP_VERSION=1.0.0
python -m uvicorn app_final:app --host 127.0.0.1 --port 8000
```

Если в числовой переменной не число (например, `FOLLOW_UP_DAYS=abc`), приложение не падает: пишет предупреждение в лог и берёт значение по умолчанию.

## Проверка работы и диагностика

Проверка, что сервис жив и какая версия запущена (во втором окне терминала, пока сервер работает):

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}

curl http://127.0.0.1:8000/version
# {"app":"Job Hunt Tracker","version":"0.1.0"}
```

Или откройте эти адреса в браузере.

### Где смотреть логи

Логи выводятся в терминал, где запущен uvicorn (стандартный вывод). Формат: время, уровень, источник, сообщение.

```
2026-10-23 12:00:00,000 INFO job_hunt_tracker: Starting Job Hunt Tracker, version 0.1.0, FOLLOW_UP_DAYS=7
2026-10-23 12:00:00,001 INFO job_hunt_tracker: Loaded 6 demo applications
2026-10-23 12:00:05,120 INFO job_hunt_tracker: GET /health -> 200 (0.6 ms)
2026-10-23 12:00:09,410 INFO job_hunt_tracker: Created application A-0007: Tailspin Toys, Data Engineer [Found]
2026-10-23 12:00:12,875 WARNING job_hunt_tracker: Application A-9999 not found
2026-10-23 12:00:12,876 INFO job_hunt_tracker: GET /applications/A-9999 -> 404 (0.5 ms)
```

- **Запуск:** версия и настройки, количество загруженных демо-откликов.
- **Запросы:** каждая строка `МЕТОД путь -> код (время)` — от middleware, через который проходят все запросы.
- **Результаты:** создание отклика, смена статуса, найденные follow-up, статистика, результат `/match`.
- **Предупреждения (`WARNING`):** несуществующий отклик, дубль, неверный `group_by`, некорректное значение переменной окружения.

### Частые проблемы

| Симптом | Причина и решение |
|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | Запущен uvicorn не из `.venv`. Активируйте окружение (`source .venv/bin/activate`) и запускайте через `python -m uvicorn` |
| `Address already in use` | Порт 8000 занят другим процессом — остановите его или запустите с `--port 8001` |
| В `/version` не та версия | Переменная `APP_VERSION` задаётся до запуска сервера; после изменения перезапустите uvicorn |

## Структура репозитория

```
├── app_final.py              # приложение: модели, правила, маршруты, логи
├── test_app.py               # автоматические тесты (pytest)
├── requirements.txt          # зависимости приложения
├── requirements-dev.txt      # + зависимости для тестов
├── .env.example              # пример переменных окружения (без секретов)
├── .gitignore
├── README.md
└── .github/workflows/ci.yml  # CI: тесты → artifact
```

## Соответствие требованиям итогового проекта

| Требование | Где выполнено | Как проверить |
|---|---|---|
| Приложение FastAPI с понятной темой | `app_final.py` | Раздел «Возможности», `/docs` |
| `/health` → `{"status": "ok"}` | `health()` | `curl /health`, тест `test_health_returns_ok` |
| `/version` | `version()` | `curl /version`, тест `test_version_returns_app_version` |
| ≥ 3 маршрута по теме | 8 маршрутов: отклики, follow-ups, stats, match | Таблица «Возможности» |
| Маршрут с параметром | `/applications/{id}`, `?status=`, `?group_by=`, `?days_ahead=` | Тесты на 404, фильтр, `group_by` |
| Настройка из переменной окружения | `APP_VERSION`, `FOLLOW_UP_DAYS`, `APPLY_NOW_THRESHOLD`, `TAILOR_THRESHOLD` | Раздел «Переменные окружения», тест `test_read_int_env_falls_back_on_invalid_value` |
| Логи: запуск, запросы, результаты | `logging`, middleware `log_requests` | Раздел «Где смотреть логи» |
| ≥ 3 доработки учебного примера | Своя тема, новые маршруты и логика, параметры, env, собственные тесты, логи, дополнительные возможности (аналитика, `/match`, защита от дублей) | Сравнение с учебным `app_final.py` |
| Нужные файлы в репозитории | Все 8 файлов из требований | Раздел «Структура репозитория» |
| Секреты не опубликованы | Секретов нет, `.env` в `.gitignore`, есть `.env.example` | `.gitignore`, `.env.example` |
| ≥ 6 осмысленных коммитов | История разработки по шагам, функция `/match` — через ветку и pull request | `git log --oneline`, вкладка Pull requests |
| ≥ 3 теста, `python -m pytest -v` | 24 теста в `test_app.py` | Раздел «Тесты» |
| CI на push и pull request | `on: push, pull_request` в `ci.yml` | Вкладка Actions, проверки в pull request |
| Artifact после успешных тестов | Job `package` с `needs: test` | Раздел Artifacts на странице запуска в Actions |
| README: назначение, установка, запуск и `/docs`, тесты, env, `/health` и `/version`, логи, запуск без `--reload` | Этот файл | Разделы выше |
