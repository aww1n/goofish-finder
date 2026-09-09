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

Заполните `BOT_TOKEN` и `ADMIN_TOKEN` в `.env`, затем запустите весь проект одной командой:

```bash
./run.sh
```

Supervisor применит миграции и запустит Telegram-бота, worker, scheduler и внутренний API.
Один `Ctrl+C` корректно остановит все процессы. Повторный параллельный запуск блокируется.

После запуска откройте бота и отправьте `/start`. API предоставляет `GET /health/live` и
`GET /health/ready`; `/admin/status` требует заголовок `Authorization: Bearer <ADMIN_TOKEN>`.

## Подключение реального источника

Для публичного web-интерфейса реализован `BrowserGoofishProvider` на Playwright. Он использует
обычный поиск сайта, постоянный профиль Chrome и не обходит CAPTCHA или проверки доступа.
Goofish может отклонять вход из автоматизированного браузера как небезопасную среду; в таком
случае provider использовать нельзя, а `GOOFISH_PROVIDER` следует оставить равным `mock` до
подключения официального или иного явно разрешённого источника.

Один раз откройте окно авторизации:

```bash
.venv/bin/python -m app.collectors.goofish.login
```

Войдите в Goofish, вернитесь в терминал и нажмите Enter. Затем установите в `.env`:

```env
GOOFISH_PROVIDER=browser
GOOFISH_BROWSER_HEADLESS=true
```

После этого перезапустите `./run.sh`. Если Goofish потребует повторный вход или покажет CAPTCHA,
provider прекратит запрос и запишет ошибку; защита источника не обходится. Для официального или
разрешённого API можно добавить другую реализацию `GoofishProvider`, не меняя worker pipeline.

## Ограничения MVP

Mock-режим полностью пригоден для разработки pipeline. Некоторые расширенные Telegram-экраны (постраничная лента, редактирование каждого поля, дайджест и подробная карточка) представлены сервисными примитивами и требуют дальнейшего UI-доведения. AI безопасно отключён и возвращает `unknown`, пока не подключён явный provider.
