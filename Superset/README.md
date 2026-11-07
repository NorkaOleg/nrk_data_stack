# nrk_data_stack - superset
Заметки по установке и настройке Superset, подключению БД в superset, разработке Datasets, Charts и Dashboards.

Установка Apache Superset в Docker (Windows + WSL2).
1. Подготовка к установке.
Проверка виртуализации. Откройте Диспетчер задач → вкладка «Производительность» → ЦП → параметр «Виртуализация» должен быть «Включено». Если выключен — зайдите в BIOS (обычно Del или F2 при загрузке) и включите Intel VT-x / AMD SVM в разделе Advanced CPU Configuration. Ctrl + R, вводите команду "optionalfeatures", должны быть включены три галочки HIPER-V, Подсистема Windows для Linux и Платформа виртуальной машины.

Установка WSL. В PowerShell от администратора:
wsl --install -d Ubuntu, если уже установлен, то wsl --update
После перезагрузки Ubuntu попросит задать имя пользователя и пароль — они локальные, для sudo. Если сразу не перешел в УЗ созданного пользователя, закрыть и открыть Ubuntu.

Установка Docker Desktop. Скачайте установщик с официального сайта docker.com. При установке отметьте «Use WSL 2 based engine». В настройках Docker Desktop → Resources → WSL Integration включите интеграцию для вашей Ubuntu. Проверка:
docker --version
docker compose version

2. Установка Superset в Ubuntu
Создаем папку в \\wsl.localhost\Ubuntu\home\dedlogoped - nrk_data_stack (задаете свое название)
Открываем терминал Ubuntu:
sudo apt update && sudo apt upgrade -y
cd ~/nrk_data_stack
git clone https://github.com/apache/superset.git
Репозиторий GitHub на версию, которую установил я https://github.com/apache/superset/tree/6.1.0
Для перехода в Ubuntu - git checkout tags/6.1.0
Переходим в каталог - cd superset

 3. Создание и настройка файлов
Оба файла лежат в папке docker/ клонированного репозитория. Нужен файл .env — переменные окружения (откуда приложение берёт секреты и настройки) тут \\wsl.localhost\Ubuntu\home\dedlogoped\nrk_data_stack\superset\docker и создать файл superset_config_docker.py — Python-конфиг, который монтируется внутрь контейнера и задаёт поведение приложения тут \\wsl.localhost\Ubuntu\home\dedlogoped\nrk_data_stack\superset\docker\pythonpath_dev

Нужно сгенерировать в Ubuntu ключ командой "openssl rand -base64 42" и добавить его в конец файла .env
SUPERSET_SECRET_KEY=<ваш ключ>
SCARF_ANALYTICS=false
Можно этой же командой сгенерировать ключ для GLOBAL_ASYNC_QUERIES_JWT_SECRET — для подписи JWT-токенов асинхронных запросов, если эту функцию не будете добавлять, то ключ не нужно генерировать и добавлять соответствующие параметры в superset_config_docker.py

После изменений перезапускаем: docker compose -f docker/docker-compose-non-dev.yml up -d
Первый запуск занимает 5–10 минут: скачиваются образы, применяются миграции, создается админ по умолчанию (admin/admin).

4. Типичные ошибки и решения
• «Refusing to start due to insecure SECRET_KEY» — ключ не задан или остался дефолтным. Сгенерируйте openssl rand -base64 42 и пропишите его и в .env (SUPERSET_SECRET_KEY), и в superset_config_docker.py (SECRET_KEY). Если ключ менялся после первого запуска — добавьте в конфиг строку PREVIOUS_SECRET_KEY = 'старый_ключ', иначе зашифрованные данные не расшифруются.
• Изменения в конфиге не применяются — файлы из docker/ подхватываются при старте контейнера, а не на лету. Нужен down + up. Если правили образ (например, добавляли драйвер БД в requirements-local.txt) — нужен docker compose ... build --no-cache superset_app.
• Порт 8088 занят — либо остановите процесс, либо в .env смените порт (SUPERSET_PORT / mapping в docker-compose).
• docker compose down -v удалил все данные — флаг -v сносит тома, включая метабазу и дашборды. Просто down — без -v, если данные нужны.
• Конфиг «не виден» — проверьте, что файл лежит именно в docker/superset_config_docker.py и имя не содержит опечаток; контейнер монтирует его в /app/superset_config_docker.py.

Если что, спрашивайте у Алисы, ошибки, которые возникали у меня, решил с помощью нее. Проверка логов - docker logs superset_init, я скидывал логи Алисе и скриншоты, в итоге пришел к решению и Superset запустился.

5. Проверка работы
docker compose -f docker/docker-compose-non-dev.yml ps
Все сервисы (superset_app, postgres, redis) должны быть в состоянии Up. Логи приложения, если что-то не так:
docker compose -f docker/docker-compose-non-dev.yml logs superset_app | tail -30
Открываем в браузере http://localhost:8088, логин admin, пароль admin (в non-dev сборке создается автоматически — смените в настройках профиля). Если вместо страницы — «connection refused», ждём ещё пару минут: миграции при первом старте идут до 10 минут.

После перезагрузки ПК, открываете Ubuntu, переходите в папку  cd ~/nrk_data_stack/superset и запускаете командой docker - compose -f docker-compose-non-dev.yml up -d

docker compose -f docker/docker-compose-non-dev.yml down - остановка всех контейнеров в Docker.