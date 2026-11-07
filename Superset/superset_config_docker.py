# ===== Общие настройки =====
import os

from celery.schedules import crontab

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY")
GLOBAL_ASYNC_QUERIES_JWT_SECRET = os.environ.get("GLOBAL_ASYNC_QUERIES_JWT_SECRET")

if not SECRET_KEY:
    raise ValueError("SUPERSET_SECRET_KEY is not set in docker/.env")

# ===== Кэш через Redis =====
CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "superset_",
    "CACHE_REDIS_HOST": os.environ.get("REDIS_HOST", "redis"),
    "CACHE_REDIS_PORT": int(os.environ.get("REDIS_PORT", 6379)),
    "CACHE_REDIS_DB": int(os.environ.get("REDIS_RESULTS_DB", 1)),
}
DATA_CACHE_CONFIG = CACHE_CONFIG
THUMBNAIL_CACHE_CONFIG = CACHE_CONFIG

# ===== Global Async Queries: кэш-бэкенд для Superset 6.1.0 =====
GLOBAL_ASYNC_QUERIES_CACHE_BACKEND = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_HOST": os.environ.get("REDIS_HOST", "redis"),
    "CACHE_REDIS_PORT": int(os.environ.get("REDIS_PORT", 6379)),
    "CACHE_REDIS_USER": "",
    "CACHE_REDIS_PASSWORD": "",
    "CACHE_REDIS_DB": 2,
    "CACHE_KEY_PREFIX": "gaq_",
    "CACHE_DEFAULT_TIMEOUT": 300,
}

# ===== Celery: асинхронные запросы и задачи =====
class CeleryConfig:
    broker_url = f"redis://{os.environ.get('REDIS_HOST', 'redis')}:6379/0"
    result_backend = f"redis://{os.environ.get('REDIS_HOST', 'redis')}:6379/1"
    worker_prefetch_multiplier = 1
    task_acks_late = True
    imports = (
        "superset.sql_lab",
        "superset.tasks.scheduler",
        "superset.tasks.thumbnails",
        "superset.tasks.cache",
    )
    beat_schedule = {
        "reports.scheduler": {
            "task": "reports.scheduler",
            "schedule": crontab(minute="*", hour="*"),
        },
        "reports.prune_log": {
            "task": "reports.prune_log",
            "schedule": crontab(minute=10, hour=0),
        },
    }

CELERY_CONFIG = CeleryConfig

# ===== Флаги фич =====
FEATURE_FLAGS = {
    # Jinja-шаблоны в SQL и подписях: {{ current_user_id() }}, {{ from_dttm }} и т.д.
    "ENABLE_TEMPLATE_PROCESSING": True,
    # Алерты и рассылка отчётов (скриншоты дашбордов по расписанию)
    "ALERT_REPORTS": True,
    "ALERT_REPORTS_FILTER": True,
    # Фильтры дашбордов: нативные и перекрёстные
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
    # Асинхронное выполнение запросов на дашбордах (нужен Redis 5.0+ и Celery)
    "GLOBAL_ASYNC_QUERIES": True,
    # Подзапросы в SQL-редакторе чартов
    "ALLOW_ADHOC_SUBQUERY": True,
    # Миниатюры дашбордов и чартов (нужен Celery)
    "THUMBNAILS": True,
    # Сохранение результатов SQL Lab на бэкенде
    "SQLLAB_BACKEND_PERSISTENCE": True,
    # Детализация по клику и drill down
    "DRILL_TO_DETAIL": True,
    "DRILL_BY": True,
    # Гибкие оси в чартах
    "GENERIC_CHART_AXES": True,
    # Расписание для SQL-запросов
    "SCHEDULED_QUERIES": True,
    # Встраивание чартов по URL
    "EMBEDDABLE_CHARTS": True,
    # SSH-туннель к базам данных
    "SSH_TUNNELING": True,
    # Row Level Security применяется и в SQL Lab
    "RLS_IN_SQLLAB": True,
    # Папки для датасетов и метрик в чарт-билдере
    "DATASET_FOLDERS": True,
    # Теги для дашбордов и чартов
    "TAGGING_SYSTEM": True,
    # Дополнительные таймшифты дат (например, "2015-01-03 : 2015-01-04")
    "DATE_RANGE_TIMESHIFTS_ENABLED": True,
    # Новая таблица на AG Grid (V2)
    "AG_GRID_TABLE_ENABLED": True,
}

# ===== SQL Lab =====
SQLLAB_TIMEOUT = 300
SQLLAB_MAX_RESULT = 100000
SQLLAB_ASYNC_TIME_LIMIT_SEC = 60 * 60

# ===== Интерфейс =====
LANGUAGES = {
    "en": {"flag": "us", "name": "English"},
    "ru": {"flag": "ru", "name": "Русский"},
}