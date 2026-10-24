# Практика 8. Безопасность контейнеров

Задание: развернуть веб-сайт с базой данных, настроить постоянное хранение и
сетевое окружение, проверить контейнер и образ сканерами, разобрать вывод и
предложить меры.

## Состав

- `app/` — Flask-приложение, Dockerfile, шаблон и стили;
- `docker-compose.yml` — два сервиса, том, сеть, лимиты и healthcheck;
- `.env.example` — шаблон переменных, `.env` создаётся локально и не входит в git;
- `scripts/render_terminal.py` — рисует PNG с выводами команд для отчёта;
- `results/` — compose ps, inspect, Trivy (txt/json), Docker Bench;
- `screenshots/` — страница сайта и скриншоты выводов;
- `Отчет_Практика8.docx` — отчёт.

## Запуск

```powershell
copy .env.example .env
docker compose up -d --build
docker compose ps
curl.exe http://127.0.0.1:8088/
```

Сайт доступен только на `127.0.0.1:8088`. База не публикует порт; приложение
ходит к ней по имени `db` внутри сети `p8_backend`. Данные лежат в томе
`p8_pgdata`.

Проверка постоянного хранения:

```powershell
docker compose restart
curl.exe http://127.0.0.1:8088/      # счётчик просмотров вырос, данные на месте
docker compose down
docker compose up -d
curl.exe http://127.0.0.1:8088/      # том не удалялся, данные сохранились
```

`docker compose down -v` удаляет том и обнуляет базу — это ожидаемо, но в
отчёте специально оговорено.

## Настройки безопасности

- приложение работает от `uid 10001`, не от root;
- корневая ФС `read_only: true` у web и db, временные каталоги — tmpfs;
- `cap_drop: ALL` у web, `no-new-privileges:true` у обоих;
- лимиты `cpus`, `mem_limit`, `pids_limit`;
- порт только на loopback;
- отдельная bridge-сеть, база недоступна с хоста;
- HEALTHCHECK в Dockerfile и compose;
- секреты через `.env`, а не через `ARG`/`ENV` в образе.

## Сканирование

Trivy:

```powershell
docker save p8-web:local -o p8-web.tar
docker save postgres:16-alpine -o p8-db.tar
docker run --rm -v "${PWD}:/work" aquasec/trivy image --input /work/p8-web.tar
docker run --rm -v "${PWD}:/work" aquasec/trivy image --input /work/p8-db.tar
docker run --rm -v "${PWD}:/work" aquasec/trivy config /work/app/Dockerfile
```

Получено: p8-web — 0 CRITICAL, 44 HIGH, 63 MEDIUM, 64 LOW, 4 UNKNOWN;
postgres:16-alpine — 1 CRITICAL (CVE-2025-68121 в Go stdlib), 25 HIGH,
32 MEDIUM, 3 LOW. Trivy config по Dockerfile — 0 misconfigurations.

Docker Bench Security запускается из официального репозитория на хосте:

```powershell
git clone --depth 1 https://github.com/docker/docker-bench-security.git
cd docker-bench-security
sh docker-bench-security.sh
```

На Docker Desktop контейнерный вариант не видит docker.sock, поэтому использован
запуск скрипта на хосте. Итог: 117 проверок, score 3. По p8 остались: postgres
запускается от root (особенность официального образа), нет AppArmor-профиля
(Docker Desktop), опубликован loopback-порт 8088. Healthcheck и CPU-лимиты
добавлены после первого прогона и в финальном выводе отсутствуют; read-only
корневая ФС для базы тоже включена.

## Ограничения

- Docker Desktop на Windows не даёт настроить AppArmor, аудит хоста и user
  namespaces, поэтому часть предупреждений Docker Bench относится к среде, а не
  к стенду.
- Образы официальные, часть CVE в базовом Debian без исправлений. Реальные меры —
  регулярная пересборка, более свежая/минимальная база, обновление Flask,
  удаление pip из runtime и сканирование в CI.
- Пароль в `.env` учебный. Для реального стенда — Docker secrets или внешнее
  хранилище.

## Защита

**Перед ответом запускаю**

```powershell
cd "Практика8_Безопасность_контейнеров"
copy .env.example .env
docker compose up -d --build
docker compose ps
curl.exe http://127.0.0.1:8088/
```

**Порядок показа**

1. Открываю `http://127.0.0.1:8088/` — таблица объектов из PostgreSQL, счётчик просмотров.
2. Показываю `docker compose ps`: оба контейнера `healthy`, у web порт `127.0.0.1:8088`.
3. В `docker-compose.yml` показываю том `p8_pgdata`, сеть `p8_backend`, `read_only`, `cap_drop`, `no-new-privileges`, лимиты.
4. Делаю `docker compose restart`, обновляю страницу — счётчик вырос, данные на месте; затем `down` и `up` без `-v` — данные снова на месте.
5. Открываю `Отчет_Практика8.docx`: скриншоты страницы, `compose ps`, Trivy, Docker Bench.
6. Показываю `results/trivy_web.txt` и `trivy_db.txt`, `results/docker_bench_clean.txt`.

**Что говорю**

Стенд состоит из Flask-приложения и PostgreSQL. Приложение работает от uid 10001, корневая ФС read-only, все capabilities сброшены, порт опубликован только на loopback. База не публикует порт и доступна приложению по имени `db` в отдельной bridge-сети. Данные лежат в именованном томе, поэтому `restart` и `down/up` их не теряют; удаляет данные только `down -v`. Trivy нашёл 175 уязвимостей в web-образе и 64 в postgres, включая одну критическую в Go stdlib; основная масса — базовый Debian. Docker Bench дал 117 проверок и score 3: на Docker Desktop недоступны AppArmor и аудит хоста, а postgres официально стартует от root, чтобы выставить владельца тома. Healthcheck, CPU-лимиты и read-only для базы я добавил после первого прогона, в финальном выводе этих замечаний уже нет.

**Вопросы, к которым готовлюсь**

- Почему score 3: Docker Desktop не даёт часть проверок хоста; по самому стенду остались root-процесс postgres, AppArmor и loopback-порт.
- Почему postgres от root: официальный entrypoint меняет владельца каталога, затем сбрасывает права; в продакшене — заранее подготовленный том и uid postgres.
- Почему не исправить все CVE: часть без патчей в текущем Debian; нужна регулярная пересборка, более свежая/минимальная база и CI-порог по CRITICAL/HIGH.
- Почему порт 8088 всё равно открыт: это нужный loopback-доступ для проверки; наружу он не публикуется.
