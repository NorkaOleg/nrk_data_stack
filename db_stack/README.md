# db_stack
db_stack - локальные базы данных. Практический гайд: реляционная БД, колоночная аналитика и векторное хранилище в одном compose-файле — с обходом всех ловушек 2026 года.

Зачем связка из трёх баз
Классический BI/AI-стек сегодня собирается из трёх хранилищ: PostgreSQL — операционные данные и метаданные, ClickHouse — аналитика на миллионах строк, Qdrant — векторный поиск для RAG и семантических запросов. Поднять их локально — час работы, если знать три ловушки, на которых ломается половина гайдов: изменившийся в PostgreSQL 18 путь данных, монтирование конфигов ClickHouse и защиту Qdrant «несуществующими» переменными. Обо всём этом — ниже, с готовыми файлами.

Окружение: Windows 10/11 + WSL2 (Ubuntu) + Docker Desktop. На Linux всё работает так же, меняются только пути к данным.

Шаг 1. Подготовка
Понадобятся:

Docker Desktop с включённым WSL2-бэкендом (или отдельно установленный Docker Engine в Ubuntu внутри WSL);
WSL2 с Ubuntu — данные будем держать на ext4-файловой системе, а не на дисках Windows. Это не эстетика: bind mount на пути /mnt/c и \wsl.localhost из Windows известен порчей хранилищ Qdrant, и разработчики чинили это отдельными релизами. 
Проверка готовности:

bash
docker --version && docker compose version
Шаг 2. Структура проекта
Все три базы живут в одной папке — так compose видит .env и относительные пути работают предсказуемо:

text
~/nrk_data_stack/db_stack/
├── docker-compose-db.yml
├── .env
└── data/            # создастся автоматически, сюда лягут данные всех трёх БД
    ├── postgres/
    ├── clickhouse/
    └── qdrant/
Важное правило: запускать compose только из этой папки — пути в .env относительные (./data/...).

Шаг 3. Файл .env
Все параметры — в одном месте, конфиг остаётся чистым и переносимым:

ini
# ==================== НАСТРОЙКИ СТЕКА БАЗ ДАННЫХ ====================
# Файл положить в ~/nrk_data_stack/db_stack рядом с docker-compose-db.yml
# ВАЖНО: запускать docker compose только из этой папки

CONTAINER_TIMEZONE=Europe/Moscow

# ---------- PostgreSQL 18 ----------
POSTGRES_CONTAINER_NAME=nrk-postgres
POSTGRES_IMAGE=postgres:18
POSTGRES_DB=nrk_db
POSTGRES_USER=nrk
POSTGRES_PASSWORD=ChangeMe_Postgres2026
POSTGRES_PORT=5432
POSTGRES_VOLUME_PATH=./data/postgres

# ---------- ClickHouse 26.8 LTS ----------
CLICKHOUSE_CONTAINER_NAME=nrk-clickhouse
CLICKHOUSE_IMAGE=clickhouse/clickhouse-server:26.8
CLICKHOUSE_DB=nrk_analytics
CLICKHOUSE_USER=nrk
CLICKHOUSE_PASSWORD=ChangeMe_Clickhouse2026
CLICKHOUSE_PORT=8123
CLICKHOUSE_NATIVE_PORT=9000
CLICKHOUSE_VOLUME_PATH=./data/clickhouse

# ---------- Qdrant v1.19 ----------
QDRANT_CONTAINER_NAME=nrk-qdrant
QDRANT_IMAGE=qdrant/qdrant:v1.19.1
QDRANT_API_PORT=6333
QDRANT_GRPC_PORT=6334
# Замените на свою длинную случайную строку (32+ символов)
QDRANT_API_KEY=ChangeMe_QdrantKey2026
QDRANT_VOLUME_PATH=./data/qdrant
Три замечания:

Пароли ChangeMe_* — заглушки. Замените перед реальным запуском; ключ Qdrant — случайная строка от 32 символов. 
Версии в тегах, не в latest. Для ClickHouse консервативная стратегия — выждать пару патч-релизов после выхода LTS-ветки, они выходят быстро. 
.env не должен попадать в git. Добавьте его в .gitignore вместе с папкой data/.
Шаг 4. docker-compose-db.yml
yaml
services:
  # ==================== PostgreSQL 18 ====================
  postgres:
    image: ${POSTGRES_IMAGE}
    container_name: ${POSTGRES_CONTAINER_NAME}
    environment:
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - TZ=${CONTAINER_TIMEZONE}
    volumes:
      # ВНИМАНИЕ (PostgreSQL 18+): данные хранятся в /var/lib/postgresql/<версия>/docker.
      # Монтируем родительский каталог /var/lib/postgresql,
      # а НЕ старый путь /var/lib/postgresql/data из прошлых гайдов!
      - ${POSTGRES_VOLUME_PATH}:/var/lib/postgresql
    ports:
      - "${POSTGRES_PORT}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    restart: unless-stopped

  # ==================== ClickHouse 26.8 LTS ====================
  clickhouse:
    image: ${CLICKHOUSE_IMAGE}
    container_name: ${CLICKHOUSE_CONTAINER_NAME}
    environment:
      - CLICKHOUSE_DB=${CLICKHOUSE_DB}
      - CLICKHOUSE_USER=${CLICKHOUSE_USER}
      - CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}
      - CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1
      - TZ=${CONTAINER_TIMEZONE}
    ports:
      - "${CLICKHOUSE_PORT}:8123"         # HTTP API и веб-консоль /play
      - "${CLICKHOUSE_NATIVE_PORT}:9000"  # native-протокол (clickhouse-client)
    volumes:
      # БЕЗ монтирования config.xml и users.xml — см. ловушку №2 в статье
      - ${CLICKHOUSE_VOLUME_PATH}:/var/lib/clickhouse
    ulimits:
      nofile:
        soft: 262144
        hard: 262144
    restart: unless-stopped

  # ==================== Qdrant v1.19 ====================
  qdrant:
    image: ${QDRANT_IMAGE}
    container_name: ${QDRANT_CONTAINER_NAME}
    ports:
      - "${QDRANT_API_PORT}:6333"   # REST API и веб-дашборд
      - "${QDRANT_GRPC_PORT}:6334"  # gRPC — нужен Python-клиенту!
    environment:
      - QDRANT__SERVICE__API_KEY=${QDRANT_API_KEY}
      - TZ=${CONTAINER_TIMEZONE}
    volumes:
      # ext4 внутри WSL — bind mount безопасен;
      # пути /mnt/c и \wsl.localhost — риск потери данных
      - ${QDRANT_VOLUME_PATH}:/qdrant/storage
      - qdrant-temp-storage:/qdrant/temp_storage
    restart: unless-stopped

volumes:
  qdrant-temp-storage:
Шаг 5. Три ловушки, на которых ломаются гайды
Ловушка 1 — путь данных PostgreSQL. С версии 18 официальный образ хранит данные в /var/lib/postgresql/18/docker, а точка монтирования объявлена как /var/lib/postgresql. Если смонтировать старый путь /var/lib/postgresql/data из гайдов пятилетней давности — контейнер либо не поднимется, либо создаст пустую базу, а данные «исчезнут» в анонимном томе. Бонус правильного пути: внутри тома данные лежат по версиям (18/docker, 19/docker), что упрощает будущий апгрейд. 
nite07.com +1

Ловушка 2 — монтирование конфигов ClickHouse. Часто в compose переносят строки вида ./clickhouse/config.xml:/etc/clickhouse-server/config.xml. Если файлов на хосте нет, Docker молча создаст на их месте пустые каталоги поверх рабочих конфигов образа — и сервер упадёт при старте с невнятной ошибкой. Пока не нужно менять конфигурацию — не монтируйте её вовсе.

Ловушка 3 — «защита» Qdrant. Переменных QDRANT__SERVICE__ADMIN__USER/PASSWORD не существует — их можно встретить в сгенерированных LLM-конфигах, и они просто игнорируются. Единственный способ закрыть API — QDRANT__SERVICE__API_KEY. Без него веб-дашборд на порту 6333 открыт всем локальным процессам. 

Шаг 6. Запуск
bash
cd ~/nrk_data_stack/db_stack
docker compose -f docker-compose-db.yml up -d
Первая загрузка образов займёт пару минут. Статус и healthcheck'и:

bash
docker compose -f docker-compose-db.yml ps
У PostgreSQL колонка STATUS должна показать healthy — значит, сработал pg_isready. Два замечания:

restart: unless-stopped — правильный вариант для compose (конструкция restart_policy из других гайдов работает только в Swarm);
переменные POSTGRES_PASSWORD применяются только при первой инициализации пустой директории данных. Сменить пароль в .env у уже созданной базы нельзя — только через SQL или пересоздание тома. 
Шаг 7. Проверка каждой базы
PostgreSQL:

bash
docker exec -it nrk-postgres psql -U nrk -d nrk_db -c "SELECT version();"
ClickHouse — HTTP-интерфейс:

bash
curl "http://localhost:8123/?query=SELECT%20version()"
и через нативный клиент:

bash
docker exec -it nrk-clickhouse clickhouse-client --user nrk --password
Веб-консоль: http://localhost:8123/play.

Qdrant — с API-ключом:

bash
curl http://localhost:6333/collections -H "api-key: ChangeMe_QdrantKey2026"
Веб-дашборд: http://localhost:6333/dashboard.

Шаг 8. Подключения из приложений
База	Строка подключения	Клиент
PostgreSQL	postgresql://nrk:***@localhost:5432/nrk_db	psycopg, SQLAlchemy, DBeaver
ClickHouse	clickhouse://nrk:***@localhost:9000/nrk_analytics	clickhouse-connect, clickhouse-driver
Qdrant	http://localhost:6333 + api_key	qdrant-client (Python)
Для Python-клиента Qdrant обязателен gRPC-порт 6334 — если открыть только REST (6333), клиент молча будет работать в медленном режиме.

Типичные проблемы и решения
Симптом	Причина	Решение
Postgres перезапускается, в логах ошибка совместимости версий	Смонтирован старый путь /data или данные от другой мажорной версии	Смонтировать /var/lib/postgresql; для апгрейда — pg_dump/restore, не переиспользовать том 
Пароль из .env «не применился»	Переменные действуют только при первой инициализации	Пересоздать том данных или сменить пароль через SQL
ClickHouse падает при старте	Смонтированы пустые config.xml/users.xml	Убрать монтирование конфигов, перезапустить
Qdrant отвечает 403	Неверный или отсутствующий api-key	Передавать заголовок api-key в каждом запросе
Данные Qdrant «повреждаются»	Папка данных на диске Windows через /mnt/c	Держать data/ на ext4 внутри WSL 
Порт 9000 занят	Конфликт с другой службой (например, MinIO)	Вынести native-порт ClickHouse в .env на свободный
Бэкап и обновление
PostgreSQL: docker exec nrk-postgres pg_dump -U nrk nrk_db > backup.sql. Апгрейд мажорной версии — только дамп/restore: каталоги данных несовместимы между мажорами, сервер откажется стартовать на старом томе. 
ClickHouse: снапшоты таблиц или копия папки data/clickhouse при остановленном контейнере.
Qdrant: встроенные снапшоты коллекций через REST API или копия data/qdrant.
Обновление патчей — docker compose pull && docker compose up -d: данные на смонтированных томах переживают пересоздание контейнеров.
