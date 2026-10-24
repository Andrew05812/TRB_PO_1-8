# Комплект практик

Колесников Андрей Юрьевич, группа БСБО-03-23, студенческий билет 23Б0099
РТУ МИРЭА, Институт кибербезопасности и цифровых технологий

Репозиторий: https://github.com/Andrew05812/TRB_PO_1-8

## Что внутри

| Папка | Что сделано | Чем проверено |
|---|---|---|
| `Практика1_Файловый_менеджер` | консольный файловый менеджер на C#/.NET 8: диски, создание/чтение/изменение/удаление файлов, JSON/XML, ZIP, SQLite, журнал действий | `dotnet build` без предупреждений, `--selfcheck` — 18 из 18 |
| `Практика2_CI_CD` | многоступенчатый `Dockerfile` и `.gitlab-ci.yml`: build → test → sast → deploy | publish, JUnit на 18 проверок, `docker build` и запуск образа, Semgrep без находок |
| `Практика3_Хеширование` | собственный переборщик `bruteforce.py`: словарь, маска, несколько процессов; сравнение с John the Ripper | 16 учебных хэшей, 12 восстановлено словарём, маски и ускорение замерены |
| `Практика4_Безопасная_авторизация` | переборщик формы DVWA, код-ревью по CWE, своя система авторизации на PHP с защитой от подбора | DVWA high: пароль найден на 20-й попытке; своя форма: блокировка после 5 неудач |
| `Практика5_Статический_анализ` | Semgrep и SonarQube по DVWA, код-ревью SQLi, sqlmap, Burp, своя страница вывода объекта на PDO | 2 находки CWE-89, sqlmap подтвердил blind SQLi, Burp 200/404, 5 проверок страницы |
| `Практика6_Бинарные_уязвимости` | вариант 3: format string, сборка 32-бит, gdb, `%p` и `%n`, исправленная версия | утечка SECRET из буфера, запись 0x42 через `%4$n`, fixed-версия не выполняет `%` |
| `Практика7_Анализ_кода` | разбор BAD_SIZEOF из Svace, заключение по эксплуатабельности | PDF `БСБО-03-23_Колесников_BAD_SIZEOF.pdf`, 2 страницы |
| `Практика8_Безопасность_контейнеров` | Flask + PostgreSQL, том, сеть, лимиты, read-only, Trivy и Docker Bench | сайт healthy, данные переживают restart/down-up, Trivy 175/64 находок, Bench 117 проверок |

Подробности — в `README_Практика1.md` … `README_Практика8.md` внутри папок.
В каждом README есть раздел «Защита»: что запустить, что показать, что сказать
и к каким вопросам готовиться.
Отчёты: `Отчет_Практика3.docx`, `Отчет_Практика4.docx`, `Отчет_Практика5.docx`,
`Отчет_Практика6.docx`, `Отчет_Практика8.docx`, а для практики 7 — PDF с именем
`БСБО-03-23_Колесников_BAD_SIZEOF.pdf`.

## Как запускалось

Практика 1:

```powershell
cd "Практика1_Файловый_менеджер\FileManagerApp"
dotnet build
dotnet bin\Debug\net8.0\FileManagerApp.dll --selfcheck
dotnet run
```

Практика 2 (подробные команды и риски локального раннера — в
`Практика2_CI_CD\README_Практика2.md`):

```powershell
cd "Практика1_Файловый_менеджер\FileManagerApp"
dotnet publish -c Release -o ..\..\publish
cd ..\..
bash "Практика2_CI_CD/scripts/run_selfcheck_as_junit.sh" publish/FileManagerApp.dll test-results.xml
docker build -t filemanagerapp:local -f Практика2_CI_CD/Dockerfile .
docker run --rm filemanagerapp:local --selfcheck
```

Практика 3:

```powershell
cd "Практика3_Хеширование"
pip install -r requirements.txt
python bruteforce.py --selftest
python bruteforce.py --lab --workers 8
python parallel_benchmark.py
python gen_report.py
```

Практика 4: DVWA поднимается в Docker на `127.0.0.1:8081`, своя форма — на
`127.0.0.1:8080`. Полные команды запуска и перебора есть в
`Практика4_Безопасная_авторизация\README_Практика4.md` и внутри
`SecureAuthApp\README.md`.

Практика 5:

```powershell
cd "Практика5_Статический_анализ"
docker run -d --name dvwa-p5 -p 127.0.0.1:8081:80 vulnerables/web-dvwa
docker run --rm -v "${PWD}/vulnerable:/src" -w /src semgrep/semgrep semgrep scan --config p/php .
docker run --rm -v "${PWD}/SecureObjectInfo:/app" -w /app php:8.3-cli `
  php tools/seed_user.php testuser "Summer2024!" --reset
docker run -d --name p5-secure -p 127.0.0.1:8082:8080 `
  -v "${PWD}/SecureObjectInfo:/app" -w /app php:8.3-cli php -S 0.0.0.0:8080 -t public
python tests/test_object_info.py
```

sqlmap и Burp описаны в `README_Практика5.md`; там же команда запуска Burp
под Xvfb.

Практика 6:

```powershell
cd "Практика6_Бинарные_уязвимости"
docker build -t p6-lab docker
docker run --rm -v "${PWD}:/lab" -w /lab p6-lab sh scripts/run_lab.sh
docker run --rm -v "${PWD}:/lab" -w /lab p6-lab gdb -q -batch -x scripts/gdb_session.txt
```

Практика 7:

```powershell
cd "Практика7_Анализ_кода"
python gen_report.py
```

Практика 8:

```powershell
cd "Практика8_Безопасность_контейнеров"
copy .env.example .env
docker compose up -d --build
curl.exe http://127.0.0.1:8088/
docker compose ps
```

Сканирование Trivy и Docker Bench — в `README_Практика8.md`.
Для Trivy образы сохраняются в tar, потому что на Windows контейнер Trivy
не видит docker.sock; для Docker Bench используется запуск скрипта на хосте
по той же причине.

## Учебные данные и ограничения

Все хэши в Практике 3 взяты из методички. Перебор в Практике 4 и sqlmap в
Практике 5 запускаются только против локального DVWA и собственной формы на
loopback; у переборщика есть проверка адреса, внешний хост без
`--allow-remote` он не тронет. Это лабораторные стенды, а не реальные
учётные записи.

Полноценный сервер GitLab с раннером не разворачивался: стадии Практики 2
проверены локально теми же командами, что записаны в `.gitlab-ci.yml`.
SonarQube Community не выполняет taint-анализ PHP, поэтому его 0 issues не
считается доказательством отсутствия SQLi — основной результат даёт Semgrep.
Docker Desktop на Windows не позволяет настроить AppArmor и часть проверок
хоста, поэтому соответствующие предупреждения Docker Bench отнесены к среде.
