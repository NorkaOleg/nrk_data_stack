# 🤖 NRK AI Tutor — локальный AI-репетитор английского в Telegram

Полностью локальный репетитор английского (и не только) для Telegram: LLM, база данных и распознавание речи работают на вашем домашнем компьютере. Никакие данные не уходят в облако, никаких API-ключей и подписок.

> Серия статей о сборке проекта — в Telegram-канале [NRK DATA STACK](https://t.me/nrk_data_stack).

## Стек

| Компонент | Роль |
|---|---|
| **Ollama** + Qwen 3.5 9B (Q4_K_M) | «Мозг» репетитора — LLM, крутится на Windows |
| **PostgreSQL** | История диалогов, профиль пользователя, статистика |
| **aiogram 3** | Telegram-бот (asyncio, Router, фильтры) |
| **asyncpg** | Пул соединений с БД |
| **faster-whisper** | Распознавание голосовых сообщений (локально, CPU) |
| **Python 3 + venv** | Окружение в Ubuntu под WSL2 |

## Архитектура

```
Telegram ⇄ aiogram-бот (Ubuntu/WSL2)
                │
                ├── PostgreSQL ── история диалогов (messages, users, user_languages)
                │
                ├── faster-whisper ── голос → текст
                │
                └── Ollama (Windows, :11434) ── Qwen 3.5 9B ── ответ репетитора
```

Бот живёт в WSL2, Ollama — на стороне Windows. Связь между ними настроена через зеркальную сеть WSL (`networkingMode=mirrored`), поэтому бот обращается к модели по обычному `localhost:11434`.

## Возможности

- 💬 Диалог с AI-репетитором с учётом уровня ученика (zero → C1)
- 🌍 Мультиязычность: активный язык и отдельный уровень для каждого
- 🧠 Память диалога: последние сообщения подгружаются из PostgreSQL в контекст
- 🎙 Голосовые сообщения: наговорил фразу — получил транскрипт и разбор
- 🤔 Индикатор «печатает…» в реальном времени, без промежуточного мусора в чате
- 🔒 Приватность: всё локально, наружу уходит только трафик Telegram

## Быстрый старт

### 1. Ollama на Windows

```powershell
# разрешаем подключения не только с localhost
[System.Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0", "User")

# зеркальная сеть для WSL
notepad $env:USERPROFILE\.wslconfig
# добавить:
# [wsl2]
# networkingMode=mirrored

wsl --shutdown
# перезапустить Ollama
```

Проверка из Ubuntu:

```bash
curl http://localhost:11434/api/tags
```

### 2. Файлы и переменные окружения

```bash
mkdir -p ~/nrk_data_stack/tutor
cd ~/nrk_data_stack/tutor
git clone <этот репозиторий> .
nano .env
```

Содержимое `.env`:

```
BOT_TOKEN=токен от @BotFather
PG_HOST=localhost
PG_PORT=5432
PG_DB=nrk_db
PG_USER=nrk
PG_PASSWORD=пароль к постгре
OLLAMA_URL=http://localhost:11434
```

### 3. PostgreSQL

Создайте базу и пользователя:

```sql
CREATE TABLE IF NOT EXISTS users (
    tg_id      BIGINT PRIMARY KEY,
    username   TEXT,
    level      TEXT DEFAULT 'B1',
    created_at TIMESTAMPTZ DEFAULT now(),
    active_lang TEXT
);

CREATE TABLE IF NOT EXISTS user_languages (
    tg_id      BIGINT REFERENCES users(tg_id),
    lang       TEXT NOT NULL,
    level      TEXT NOT NULL DEFAULT 'zero',
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (tg_id, lang)
);

CREATE TABLE IF NOT EXISTS messages (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT REFERENCES users(tg_id),
    lang       TEXT,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_user
    ON messages (tg_id, lang, created_at);
```

### 4. Окружение и запуск

```bash
sudo apt install -y python3-venv python3-pip
python3 -m venv venv
source venv/bin/activate
pip install aiogram asyncpg ollama python-dotenv faster-whisper
python bot.py
```

Ожидаемо: `Bot is running. Ctrl+C to stop.`

Первое сообщение к модели может занять 30–60 секунд — Qwen 9B загружается в оперативную память. Дальше ответы идут мгновенно.

## Структура репозитория

```
tutor/
├── bot.py         # Telegram-бот: обработчики, интеграции Ollama/Whisper/Postgres
├── schema.sql     # Схема БД
├── .env           # Секреты (в git не попадает — см. .env.example)
├── .env.example   # Шаблон переменных окружения
└── README.md
```

## Известные грабли

<details>
<summary><b>llama-server binary not found (status 500)</b></summary>

Обновление Ollama поверх старой версии может не донести рантайм (`lib\ollama\llama-server.exe`). Решение: полностью удалить Ollama (модели в `C:\Users\<user>\.ollama\models` не пострадают), поставить начисто с [ollama.com](https://ollama.com), проверить наличие папки `lib\ollama`, перезапустить. Совет из ошибки про `cmake` игнорируйте — он для сборки из исходников.
</details>

<details>
<summary><b>Connection refused из Ubuntu</b></summary>

Ollama слушает только 127.0.0.1, а WSL2 работает в NAT-режиме. Нужны все три шага из «Быстрого старта»: `OLLAMA_HOST=0.0.0.0`, `networkingMode=mirrored`, `wsl --shutdown`.
</details>

<details>
<summary><b>Первый запрос «висит»</b></summary>

Это разогрев: модель грузится с диска в RAM. Не паникуем, ждём.
</details>

## Roadmap

- [x] Текстовый диалог с памятью
- [x] Мультиязычность и уровни
- [ ] Голосовые сообщения (Whisper)
- [ ] Ответы бота голосом (TTS — Silero)
- [ ] /stats — статистика ошибок из PostgreSQL
- [ ] Оценка произношения по транскрипту
- [ ] Автозапуск через systemd
- [ ] Аналитика на Superset
- [ ] RAG

## Автор

NRK DATA STACK — канал о данных, BI и AI-проектах своими руками.
