# ActivityBot

Discord-бот (микросервис) для трекинга голосовой активности и проведения конкурсов.

---

## Что делает

| Фича | Описание |
|------|----------|
| Трекинг войса | Считает время каждого участника в голосовых каналах выбранной категории |
| `/activity stats` | Показывает лидерборд за активный конкурс или последние 7 дней |
| `/activity contest <day\|week\|month>` | Запускает конкурс активности на выбранный период (только по ролям) |
| Авто-финиш | Каждые 30 минут проверяет окончание конкурса и публикует победителя в канал |
| Persist через Redis | Join-timestamps хранятся в Redis (appendonly) — трекинг не прерывается при рестарте бота |

---

## Архитектура

```
ActivityBot (микросервис)
├── bot.py                        # ActivityBot: get_cfg(), HydraBot base
├── data/config.py                # ActivityConfig — конфиг гильдии
└── cogs/
    ├── voice_tracker/
    │   └── __init__.py           # on_voice_state_update: join/leave в Redis → сессии в DB
    ├── activity/
    │   ├── commands.py           # /activity stats, /activity contest, contest_watcher task
    │   ├── containers.py         # билдеры Container-компонентов
    │   └── utils.py              # medal(), format_duration(), time_left(), has_contest_permission()
    └── error_logger/             # отправка ошибок в Telegram через Redis
```

---

## Как работает трекинг

1. Участник входит в войс-канал из отслеживаемой категории → `activity:voice:{user_id}` = unix timestamp (Redis)
2. Участник выходит → читает timestamp, вычисляет duration, сохраняет сессию в DB через `/activity/sessions`
3. При рестарте бота `_sync_on_ready()` сканирует все каналы категории и восстанавливает Redis-ключи для уже присутствующих участников (если ключа нет — записывает текущее время)

Сессии короче 30 секунд игнорируются.

---

## Конкурсы

- Запускает участник с нужной ролью: `/activity contest day|week|month`
- Предыдущий активный конкурс автоматически деактивируется
- Каждые 30 минут `_contest_watcher` проверяет `ends_at`, при истечении:
  - Запрашивает топ-5 участников за период конкурса
  - Публикует `build_contest_ended_container` в `activity_results_channel_id`
  - Помечает конкурс завершённым

---

## Конфиг гильдии (`guild.yaml` + `roles.yaml`)

| Ключ | Тип | Описание |
|------|-----|----------|
| `activity_tracked_category_id` | int \| null | ID категории каналов для трекинга |
| `activity_excluded_channel_ids` | list[int] | Каналы внутри категории, которые не считаются |
| `activity_contest_role_ids` | list[int] | Роли, которым разрешено запускать конкурс |
| `activity_results_channel_id` | int \| null | Канал для анонса победителей |

---

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `DISCORD_TOKEN` | Токен Discord-бота (`ACTIVITY_DISCORD_TOKEN` в `.env`) |
| `DB_API_URL` | URL DB-API (default `http://db-api:8000`) |
| `DB_API_KEY` | Ключ авторизации к DB-API |
| `CORE_URL` | URL core-service (default `http://core:8001`) |
| `REDIS_URL` | Redis (default `redis://redis:6379/0`) |
| `ENABLED` | `true`/`false` — выключить без удаления кода |

> `guild_id` бот узнаёт из core (`guild.yaml`) при старте — env-переменной нет.

---

## Запуск

```bash
# Из корня проекта BotEco-Redis
make restart-svc SVC=activity-bot     # перезапустить
make rebuild-svc SVC=activity-bot     # пересобрать и перезапустить
make logs-svc    SVC=activity-bot     # логи
```

---

## Стек

- **Python 3.12** + **disnake 2.12** — Discord бот (Component v2)
- **Redis** — хранение join-timestamps с appendonly persistence
- **PostgreSQL** (через DB-API) — сессии и конкурсы
- **structlog** — структурированные логи
- **Pydantic v2** — типизация конфига
- **uv** — менеджер зависимостей
