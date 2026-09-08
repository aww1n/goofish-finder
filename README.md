# GOFISH FINDER

Telegram-бот для мониторинга объявлений Goofish. По умолчанию запускается с детерминированным `MockGoofishProvider`; неизвестные или неавторизованные endpoint'ы Goofish не используются. Проект не обходит CAPTCHA, антибот-защиту или ограничения источника.

## Возможности

- inline-first Telegram UX и FSM создания поиска;
- PostgreSQL/SQLAlchemy 2 + Alembic, soft delete и проверка владельца callback-действий;
- Celery/Redis scheduler, worker pool, backoff и идемпотентные alerts;
- сырые и нормализованные данные, дедупликация и история цены;
- hard-фильтры, market median, Deal Score с breakdown и Risk Score;
- structured-first распознавание 验货宝, безопасные DOM/metadata/OCR fallback-сигналы и обязательный search filter;
- избранное, скрытие, лимит уведомлений и тихие часы на сервисном уровне;
- внутренние FastAPI health/admin endpoints.

## Запуск без Docker

Требуются Python 3.12+, PostgreSQL и Redis, запущенные локально или доступные по сети.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# создайте БД и укажите подключения в DATABASE_URL и REDIS_URL
alembic upgrade head
pytest
```

Заполните `BOT_TOKEN` и `ADMIN_TOKEN` в `.env`, затем запустите процессы в отдельных терминалах:

```bash
python -m app.main
celery -A app.workers.celery_app:celery_app worker -Q searches,notifications -l INFO
celery -A app.workers.celery_app:celery_app beat -l INFO
uvicorn app.api.main:app --reload
```

После запуска откройте бота и отправьте `/start`. API предоставляет `GET /health/live` и
`GET /health/ready`; `/admin/status` требует заголовок `Authorization: Bearer <ADMIN_TOKEN>`.

## Подключение реального источника

Реализуйте `GoofishProvider` в отдельном модуле только для документированного и разрешённого способа доступа. URL, ключи и авторизацию передавайте через настройки; бизнес-логика и worker менять не требуется. При rate limit provider должен выбрасывать `ProviderRateLimited` с допустимым `retry_after`.

## Ограничения MVP

Mock-режим полностью пригоден для разработки pipeline. Некоторые расширенные Telegram-экраны (постраничная лента, редактирование каждого поля, дайджест и подробная карточка) представлены сервисными примитивами и требуют дальнейшего UI-доведения. AI безопасно отключён и возвращает `unknown`, пока не подключён явный provider.
