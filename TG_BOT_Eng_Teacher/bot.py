# ============================================================
# bot.py — Telegram-бот репетитор с локальной LLM (Ollama)
# Стек: aiogram 3.x + asyncpg (Postgres) + ollama (локальная модель)
# ============================================================

# --- Импорт стандартной библиотеки ---
import asyncio   # асинхронность: запускаем долгие операции (запрос к Ollama) в отдельном потоке,
                 # чтобы бот не «зависал» и продолжал отвечать другим пользователям
import os        # чтение переменных окружения из .env (токен, пароли — не храним в коде)

# --- Сторонние библиотеки (ставятся через pip) ---

# asyncpg — быстрый асинхронный драйвер PostgreSQL: соединения с базой, запросы
import asyncpg

# официальный клиент Ollama — библиотека-обёртка над HTTP API локальной модели
import ollama

# aiogram 3 — фреймворк для Telegram-ботов. Импортируем нужные классы:
from aiogram import Bot, Dispatcher, F
#   Bot         — объект, через который шлём сообщения в Telegram
#   Dispatcher  — «маршрутизатор»: решает, какой обработчик вызвать на каждое входящее событие
#   F           — «магический фильтр» (F.text, F.data...) для проверки содержимого сообщения

from aiogram.filters import Command, CommandStart
#   CommandStart — фильтр на команду /start; Command — на любую другую (/lang, /level, /reset)

from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
#   Message              — входящее сообщение от пользователя
#   CallbackQuery        — нажатие на inline-кнопку (язык/уровень — это кнопки)
#   InlineKeyboardMarkup — контейнер для кнопок, прилагается к сообщению
#   InlineKeyboardButton — одна кнопка

# python-dotenv — подгружает файл .env в переменные окружения (в .env лежат токен и пароли)
from dotenv import load_dotenv

# Читаем .env из текущей папки: BOT_TOKEN, PG_HOST и т.д. становятся доступны через os.getenv()
load_dotenv()

# Имя модели в Ollama — та самая, что вы скачали (проверка: ollama list).
# Если захотите другую модель — меняется только эта строка.
MODEL = "qwen3.5:9b"

# Клиент Ollama: явно указываем адрес сервера (он запущен в Windows,
# в WSL доступен через localhost:11434 — это проверено curl'ом)
ollama_client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))

# Сколько последних реплик диалога отправлять модели как «память».
# 10 = 5 вопросов + 5 ответов. Больше — модель лучше помнит контекст, но медленнее отвечает.
HISTORY_LIMIT = 10

# --- Справочники ---

# Код языка -> название по-русски. Название попадает в промпт для модели и в текст кнопок.
# Хотите добавить язык — просто добавьте строку сюда (например, "ar": "арабский"),
# таблица и клавиатура подхватят его автоматически.
LANGUAGES = {
    "en": "английский",
    "de": "немецкий",
    "fr": "французский",
    "es": "испанский",
    "it": "итальянский",
    "zh": "китайский",
    "ja": "японский",
    "ko": "корейский",
    "tr": "турецкий",
}

# Код уровня -> человеческое название. "zero" — специальный режим «с самого нуля».
# Значения хранятся в БД (user_languages.level), поэтому менять ключи после запуска не стоит —
# только добавлять новые.
LEVELS = {
    "zero": "С нуля (не знаю даже алфавита)",
    "A1": "A1 — начинающий",
    "A2": "A2 — элементарный",
    "B1": "B1 — средний",
    "B2": "B2 — выше среднего",
    "C1": "C1 — продвинутый",
    "C2": "C2 — свободное владение",
}


def build_system_prompt(level: str, lang_name: str) -> str:
    """Собирает «системный промпт» — инструкцию для модели, кто она и как себя вести.

    Системный промпт модели отправляется ПЕРВЫМ сообщением в каждом запросе (не пишется в БД) —
    так модель каждый раз получает правила игры. Уровень ученика подставляется в текст.
    """
    # --- Режим «с нуля»: совсем другой стиль общения ---
    if level == "zero":
        return f"""Ты — дружелюбный носитель {lang_name} языка и терпеливый репетитор.
Ученик изучает {lang_name} с ПОЛНОГО НУЛЯ: он не знает даже алфавита.
Правила:
- Начинайте с самых основ: алфавит/иероглифы, произношение, простейшие фразы приветствия.
- Объяснения давай на русском. Фразы изучаемого языка пиши с транскрипцией:
  для китайского — пиньинь, для японского — ромадзи, для остальных — русская транскрипция.
- Вводи не больше 1-2 новых фраз или букв за одно сообщение.
- В конце сообщения давай мини-блок:
  ✏️ новые слова: <слово — перевод — транскрипция>
- Заканчивай простым вопросом или заданием на повторение изученного.
- Отвечай компактно: 3-6 предложений."""
    # --- Режим C2: продвинутый, с идиомами и нюансами ---
    if level == "C2":
        return f"""Ты — дружелюбный носитель {lang_name} языка и репетитор.
Уровень ученика: C2 (почти свободное владение).
Правила:
- Говори на {lang_name} естественно и живо, как в реальном разговоре с носителем: идиомы, устойчивые выражения, тонкие нюансы.
- Мягко исправляй даже мелкие неточности, отмечай стилистические нюансы.
- В конце сообщения блок:
  ✏️ corrections: <замечания, максимум 2>
- Задавай встречные вопросы на сложные темы.
- Отвечай компактно: 2-5 предложений."""
    # --- Все остальные уровни: один шаблон с подстановкой уровня ---
    return f"""Ты — дружелюбный носитель {lang_name} языка и репетитор.
Уровень ученика: {level}.
Правила:
- Отвечай на {lang_name} простыми структурами, соответствующими уровню ученика.
- Мягко исправляй ошибки: сначала естественно продолжи диалог, затем дай краткий разбор в конце сообщения в формате:
  ✏️ corrections: <перечисли ошибки и правильные варианты, максимум 2; объяснения на русском>
- Задавай встречные вопросы, чтобы разговор не затухал.
- В основной реплике не переходи на русский; русский — только для разбора ошибок.
- Отвечай компактно: 2-4 предложения."""


def lang_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """Строит сетку кнопок выбора языка: по 3 кнопки в ряд.

    prefix — префикс callback-данных. При нажатии Telegram вернёт боту строку вида
    "lang:en" (или "pick:en" — смотря какой префикс передали). Так один и тот же
    генератор клавиатуры обслуживает и выбор языка, и будущие сценарии.
    """
    rows = []                    # сюда соберём ряды кнопок
    codes = list(LANGUAGES)      # список кодов языков: ["en", "de", ...] в порядке словаря
    for i in range(0, len(codes), 3):          # шаг по 3 элемента
        rows.append([
            InlineKeyboardButton(text=LANGUAGES[c].capitalize(),  # надпись на кнопке: "Английский"
                                 callback_data=f"{prefix}:{c}")   # скрытые данные: "lang:en"
            for c in codes[i:i + 3]                               # срез из 3 кодов
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)   # клавиатура из рядов


def level_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Строит кнопки выбора уровня (по 2 в ряд) для конкретного языка.

    В callback зашиваем и язык, и уровень: "lvl:en:B1" — чтобы обработчик нажатия
    знал, к какому языку относится выбор, даже если пользователь к тому моменту
    что-то ещё понажимал.
    """
    rows = []
    codes = list(LEVELS)
    for i in range(0, len(codes), 2):          # по 2 кнопки в ряд
        rows.append([
            InlineKeyboardButton(text=LEVELS[c],                        # надпись: "B1 — средний"
                                 callback_data=f"lvl:{lang}:{c}")       # данные: "lvl:en:B1"
            for c in codes[i:i + 2]
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# Работа с базой данных
# ============================================================

async def get_db_pool():
    """Создаёт пул соединений с Postgres.

    Пул — это несколько «готовых» соединений, которые переиспользуются. Создавать новое
    соединение на каждый запрос дорого; пул держит 1..5 соединений и раздаёт их по мере
    надобности. Параметры берём из .env, пароль — только оттуда, в коде его нет.
    """
    return await asyncpg.create_pool(
        host=os.getenv("PG_HOST"),          # "localhost" — база в Docker на этой же машине
        port=int(os.getenv("PG_PORT")),     # 5432 — стандартный порт Postgres
        database=os.getenv("PG_DB"),        # nrk_db
        user=os.getenv("PG_USER"),          # nrk
        password=os.getenv("PG_PASSWORD"),  # пароль из .env
        min_size=1,                         # минимум соединений в пуле
        max_size=5,                         # максимум (для домашнего бота с запасом)
    )


async def save_message(pool, tg_id: int, lang: str, role: str, content: str):
    """Сохраняет одну реплику диалога в БД.

    role — кто говорил: "user" (ученик) или "assistant" (бот/модель).
    $1, $2, $3, $4 — параметры запроса. asyncpg подставляет их БЕЗ склейки строк,
    поэтому SQL-инъекции невозможны. Это не просто стиль, а обязательное правило.
    """
    await pool.execute(
        "INSERT INTO messages (tg_id, lang, role, content) VALUES ($1, $2, $3, $4)",
        tg_id, lang, role, content,
    )


async def get_history(pool, tg_id: int, lang: str) -> list[dict]:
    """Возвращает последние HISTORY_LIMIT реплик диалога в формате для Ollama.

    Логика:
    1. Берём последние N записей (ORDER BY created_at DESC — новые сверху, LIMIT отрезает хвост).
    2. Приворачиваем каждую строку БД к виду {"role": ..., "content": ...} — именно такой
       формат ждёт API моделей.
    3. reversed() переворачивает обратно в хронологический порядок: старые реплики раньше,
       новые последними. Модель видит диалог как реальную переписку.
    Фильтр по lang разделяет истории: немецкий диалог не «протекает» в английский.
    """
    rows = await pool.fetch(
        """SELECT role, content FROM messages
           WHERE tg_id = $1 AND lang = $2 ORDER BY created_at DESC LIMIT $3""",
        tg_id, lang, HISTORY_LIMIT,
    )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def ask_tutor(pool, tg_id: int, lang: str, level: str, text: str) -> str:
    """Главный «мозг» бота: готовит контекст, спрашивает модель, сохраняет ответ.

    Шаги:
    1. Сохраняем реплику ученика в БД (сначала пишем — потом спрашиваем модель: если
       запрос упадёт, реплика всё равно останется в истории).
    2. Достаём историю диалога.
    3. Склеиваем: системный промпт (правила) + история + уже сохранённая новая реплика.
       Итоговый список messages выглядит так: [system, user1, assistant1, ..., userN].
    4. Отправляем в Ollama и забираем ответ.
    5. Сохраняем ответ бота в БД.
    6. Возвращаем текст ответа вызывающему коду.
    """
    lang_name = LANGUAGES[lang]                             # "en" -> "английский" — для текста промпта
    await save_message(pool, tg_id, lang, "user", text)     # шаг 1
    history = await get_history(pool, tg_id, lang)          # шаг 1
    messages = [{"role": "system", "content": build_system_prompt(level, lang_name)}] + history # шаг 1
    # Тяжёлый вызов модели — в отдельный поток, чтобы бот не замерзал на время генерации
    response = await asyncio.to_thread(ollama_client.chat, model=MODEL, messages=messages, think=False)
    answer = response["message"]["content"].strip()         # достаём текст, обрезаем пробелы
    await save_message(pool, tg_id, lang, "assistant", answer)  # шаг 5
    return answer                                           # шаг 6


async def upsert_user(pool, m: Message):
    """Регистрирует/обновляет пользователя.

    INSERT ... ON CONFLICT ... DO UPDATE — «встать, если нет; обновить, если есть»
    (upsert). Имя пользователя в Telegram меняется — обновляем при каждом заходе.
    Если username у пользователя нет (m.from_user.username is None) — запишется NULL,
    это нормально.
    """
    await pool.execute(
        """INSERT INTO users (tg_id, username)
           VALUES ($1, $2)
           ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username""",
        m.from_user.id, m.from_user.username,
    )


async def get_active_lang(pool, tg_id: int) -> str | None:
    """Возвращает активный язык пользователя ("en", "de"...) или None, если ещё не выбрал.

    fetchval возвращает значение первой колонки первой строки (или None, если пусто) —
    удобно для запросов «дай одно значение».
    """
    return await pool.fetchval("SELECT active_lang FROM users WHERE tg_id = $1", tg_id)


# ============================================================
# Обработчики — сердце бота. Диспетчер сам вызывает нужную функцию
# на каждое входящее событие.
# ============================================================

async def main():
    # Создаём объект бота: токен берём строго из .env (в коде секрета нет)
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    # Диспетчер — маршрутизатор событий, регистрируем на нём обработчики ниже
    dp = Dispatcher()
    # Пул соединений с базой — создаём один раз и передаём всем обработчикам
    pool = await get_db_pool()

    # --- /start ---
    # Регистрируем обработчик декоратором: "@dp.message(фильтр)" означает
    # «на сообщения, прошедшие фильтр, вызывай эту функцию».
    @dp.message(CommandStart())
    async def start(m: Message):
        await upsert_user(pool, m)                      # регистрируем/обновляем пользователя
        active = await get_active_lang(pool, m.from_user.id)
        if active:
            # Пользователь уже настроен — короткая справка вместо повторного опроса
            await m.answer(
                f"Your current language: {LANGUAGES[active]}.\n"
                f"Change it with /lang, level with /level, history with /reset."
            )
        else:
            # Новичок — показываем клавиатуру выбора языка
            await m.answer("Привет! Какой язык будем учить? Выберите из списка 👇",
                           reply_markup=lang_keyboard("lang"))

    # --- Нажатие кнопки языка ---
    # F.data.startswith("lang:") — фильтр: сработать только на callback-данные,
    # начинающиеся с "lang:" (то есть на кнопки, порождённые lang_keyboard("lang")).
    @dp.callback_query(F.data.startswith("lang:"))
    async def pick_lang(c: CallbackQuery):
        lang = c.data.split(":")[1]   # из "lang:en" достаём "en"
        # Добавляем язык пользователю, если его ещё нет (ON CONFLICT DO NOTHING —
        # если пара уже существует, просто ничего не делаем, без ошибки)
        await pool.execute(
            """INSERT INTO user_languages (tg_id, lang) VALUES ($1, $2)
               ON CONFLICT (tg_id, lang) DO NOTHING""",
            c.from_user.id, lang,
        )
        # Отвечаем сообщением с клавиатурой уровней.
        # c.message — исходное сообщение с кнопками; отвечаем на него новым сообщением.
        await c.message.answer(
            f"Выбран язык: {LANGUAGES[lang]}.\nКакой у вас уровень?",
            reply_markup=level_keyboard(lang),
        )
        # c.answer() — «отжать» кнопку: убрать часики-загрузку на кнопке в Telegram.
        # Без этого кнопка крутится ~10 секунд и выглядит сломанной.
        await c.answer()

    # --- Нажатие кнопки уровня ---
    @dp.callback_query(F.data.startswith("lvl:"))
    async def pick_level(c: CallbackQuery):
        # callback вида "lvl:en:B1": распаковываем. Символ _ — «префикс нам не нужен».
        _, lang, level = c.data.split(":")
        # 1) Сохраняем уровень для выбранного языка
        await pool.execute(
            "UPDATE user_languages SET level = $1 WHERE tg_id = $2 AND lang = $3",
            level, c.from_user.id, lang,
        )
        # 2) Делаем этот язык активным. Две команды — подстраховка:
        #    UPDATE сработает, если пользователь уже есть в таблице users,
        #    INSERT ... ON CONFLICT — если записи ещё нет (первый запуск).
        #    Так активный язык точно окажется записан в обоих случаях.
        await pool.execute(
            "UPDATE users SET active_lang = $1 WHERE tg_id = $2", lang, c.from_user.id,
        )
        await pool.execute(
            "INSERT INTO users (tg_id, active_lang) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET active_lang = $2",
            c.from_user.id, lang,
        )
        await c.message.answer(
            f"Готово! Учим {LANGUAGES[lang]}, уровень: {LEVELS[level]}.\n"
            "Пишите мне на изучаемом языке (или попросите помочь начать) — я отвечу как носитель."
        )
        await c.answer()

    # --- /lang — список языков + выбор/добавление ---
    @dp.message(Command("lang"))
    async def change_lang(m: Message):
        await upsert_user(pool, m)
        # Берём все языки пользователя с их уровнями
        rows = await pool.fetch(
            "SELECT lang, level FROM user_languages WHERE tg_id = $1", m.from_user.id
        )
        # Формируем список строк вида "• Английский — B1 — средний".
        # Тенарный оператор: если rows пуст — другой текст.
        text = "Изучаемые языки:\n" + "\n".join(
            f"• {LANGUAGES[r['lang']]} — {LEVELS.get(r['level'], r['level'])}" for r in rows
        ) if rows else "Пока ни одного языка не добавлено."
        # .get(..., ...) со запасом: если в БД вдруг старое/нестандартное значение уровня —
        # покажем его как есть, а не упадём с ошибкой.
        await m.answer(f"{text}\n\nВыберите язык для практики (или добавьте новый):",
                       reply_markup=lang_keyboard("lang"))

    # --- /level — сменить уровень активного языка ---
    @dp.message(Command("level"))
    async def change_level(m: Message):
        lang = await get_active_lang(pool, m.from_user.id)
        if not lang:
            # Язык ещё не выбран — некому менять уровень
            await m.answer("Сначала выберите язык: /lang или /start")
            return
        await m.answer(f"Текущий уровень для {LANGUAGES[lang]}. Выберите новый:",
                       reply_markup=level_keyboard(lang))

    # --- /reset — очистить историю активного языка ---
    @dp.message(Command("reset"))
    async def reset(m: Message):
        lang = await get_active_lang(pool, m.from_user.id)
        if lang:
            # Удаляем ТОЛЬКО историю активного языка: немецкие диалоги останутся целы
            await pool.execute(
                "DELETE FROM messages WHERE tg_id = $1 AND lang = $2", m.from_user.id, lang
            )
            await m.answer(f"History for {LANGUAGES[lang]} cleared. Let's start fresh!")
        else:
            await m.answer("Сначала выберите язык: /lang")

    # --- Ловушка для обычного текста ---
    # Регистрируется ПОСЛЕДНИМ: aiogram проверяет обработчики в порядке регистрации,
    # поэтому команды /start, /lang и кнопки обработаются раньше, а сюда попадёт
    # только «всё остальное» — обычный текст диалога.
    @dp.message(F.text)
    async def chat(m: Message):
        lang = await get_active_lang(pool, m.from_user.id)
        if not lang:
            # Пишут текст без выбора языка — вежливо показываем выбор ещё раз
            await m.answer("Привет! Давай начнём: какой язык будем учить?",
                           reply_markup=lang_keyboard("lang"))
            return
        # Достаём уровень для активного языка
        row = await pool.fetchrow(
            "SELECT level FROM user_languages WHERE tg_id = $1 AND lang = $2",
            m.from_user.id, lang,
        )
        # fetchrow вернёт None, если пары нет — на этот случай уровень по умолчанию
        level = row["level"] if row else "zero"
        # Мгновенный ответ «думаю...» — чтобы пользователь понимал, что его услышали.
        # Модель отвечает 5-30 секунд, без этого сообщения бот выглядит мёртвым.
        await m.answer("🤔 Thinking...")
        try:
            # Запрос к Ollama может занять десятки секунд. asyncio.to_thread выполняет
            # функцию в отдельном потоке, не блокируя event loop — бот остаётся отзывчивым
            # для всех остальных пользователей, пока один ждёт ответ модели.
            answer = await ask_tutor(pool, m.from_user.id, lang, level, m.text)
        except Exception as e:
            # Любая ошибка Ollama (модель не загружена, нет памяти, таймаут) — не роняем
            # бота, а показываем текст ошибки пользователю: сразу видно, что случилось.
            answer = f"Ollama error: {e}"
        await m.answer(answer)

    print("Bot is running. Ctrl+C to stop.")
    try:
        # start_polling — бесконечный цикл: сам получает обновления от Telegram
        # (long polling) и раздаёт их диспетчеру. Работает, пока не нажать Ctrl+C.
        await dp.start_polling(bot)
    finally:
        # finally выполняется в любом случае выхода (в том числе по Ctrl+C):
        # аккуратно закрываем соединения с базой, чтобы не оставлять «висящие» сессии.
        await pool.close()


# Точка входа: если файл запущен напрямую (python bot.py), а не импортирован, — стартуем.
# asyncio.run(main()) — запускает асинхронную функцию main и крутит event loop до её конца.
if __name__ == "__main__":
    asyncio.run(main())