# Практика 5. Статический анализ кода и SQL-инъекция

Работа сделана по заданию: найти SQL-инъекцию в DVWA статическим анализатором,
разобрать код, проверить уязвимость sqlmap и Burp, а затем сделать свою страницу
вывода объекта, устойчивую к SQL-инъекции.

## Что лежит в каталоге

- `vulnerable/dvwa/sqli/low.php`, `medium.php` — исходники DVWA, скопированные из контейнера.
- `vulnerable/dvwa/sqli_blind/low.php` — исходник blind-модуля.
- `sonar-project.properties`, `results/sonar_*.json` — настройка и результаты SonarQube.
- `results/semgrep.json`, `semgrep_summary.txt` — находки Semgrep.
- `results/sqlmap_blind.log`, `sqlmap_dump.log` — вывод sqlmap.
- `burp/` — конфигурация Burp, скриншот HTTP history, Dockerfile для запуска под Xvfb.
- `SecureObjectInfo/` — защищённая страница на PHP 8.3 + PDO/SQLite.
- `tests/test_object_info.py` — проверки защищённой страницы.
- `Отчет_Практика5.docx` — отчёт.

## 1. Поднять DVWA

```powershell
docker run -d --name dvwa-p5 -p 127.0.0.1:8081:80 vulnerables/web-dvwa
```

Открыть `http://127.0.0.1:8081`, войти `admin` / `password`, нажать
`Create / Reset Database`, затем в `DVWA Security` выбрать `low`.
Если база уже создана, повторять setup не нужно.

## 2. Статический анализ

Semgrep:

```powershell
docker run --rm -v "${PWD}/vulnerable:/src" -w /src semgrep/semgrep semgrep scan --config p/php .
```

Ожидаемый результат: два finding уровня ERROR, CWE-89, в
`dvwa/sqli/low.php:8` и `dvwa/sqli_blind/low.php:8`.

SonarQube (дополнительно):

```powershell
docker run -d --name sonarqube-p5 -p 127.0.0.1:9000:9000 -e SONAR_ES_BOOTSTRAP_CHECKS_DISABLE=true sonarqube:community
```

После статуса `UP` создать проект `dvwa-p5` и токен, затем запустить сканер:

```powershell
docker run --rm --add-host=host.docker.internal:host-gateway `
  -e SONAR_HOST_URL=http://host.docker.internal:9000 `
  -e SONAR_TOKEN=<токен> -v "${PWD}:/usr/src" sonarsource/sonar-scanner-cli
```

В Community-сборке PHP-анализатор не выполняет taint-анализ, поэтому по SQLi
там будет 0 issues. Это указано в отчёте; основной результат — Semgrep.

## 3. sqlmap

Нужна cookie авторизованной сессии DVWA (`PHPSESSID`) и cookie `security=low`.
Команда:

```powershell
docker run --rm --add-host=host.docker.internal:host-gateway parrotsec/sqlmap `
  -u "http://host.docker.internal:8081/vulnerabilities/sqli_blind/?id=1&Submit=Submit" `
  --cookie="PHPSESSID=<SID>; security=low" -p id --batch --dbms=MySQL `
  --technique=B --current-db --dbs
```

Получено: boolean-based blind, MySQL/MariaDB, current database `dvwa`.
Дамп строки `users` лежит в `results/sqlmap_dump.log`; пароль администратора
в учебной базе — MD5 от `password`.

## 4. Burp Suite

Burp Community не имеет headless-режима, поэтому он запускается в контейнере
с Xvfb. Сборка описана в `burp/Dockerfile`. Нужен установленный Burp
Community; его jar и каталог `burpbrowser` монтируются с хоста:

```powershell
docker build -t burp-p5 burp
docker run -d --name burp-p5 -p 127.0.0.1:8085:8085 `
  -v "<путь к BurpSuiteCommunity>:/burp/app:ro" `
  -v "${PWD}/burp:/burp/out" --entrypoint sh burp-p5 -c `
  "Xvfb :99 -screen 0 1280x1024x24 -ac >/tmp/xvfb.log 2>&1 & export DISPLAY=:99; exec java -jar /burp/app/burpsuite_community.jar --config-file=/burp/out/burp_config.json --project-file=/burp/out/p5.burp"
```

В окне Burp нужно принять лицензию, открыть Temporary project и добавить
listener: `Proxy → Proxy settings → Add → 8085, All interfaces`. После этого
запросы можно отправлять через `http://127.0.0.1:8085`. Скриншот HTTP history:
`burp/burp_history_selected.png`. Первый запрос (`id=1' AND 1=1-- -`) даёт
200 и «User ID exists», второй (`id=1' AND 1=2-- -`) — 404 и «User ID is
MISSING»; этого достаточно, чтобы вручную подтвердить булевую инъекцию.

## 5. Защищённая страница

PHP на хосте не нужен, всё запускается в контейнере `php:8.3-cli`.
Создать пользователя:

```powershell
docker run --rm -v "${PWD}/SecureObjectInfo:/app" -w /app php:8.3-cli `
  php tools/seed_user.php testuser "Summer2024!" --reset
```

Запустить встроенный сервер:

```powershell
docker run -d --name p5-secure -p 127.0.0.1:8082:8080 `
  -v "${PWD}/SecureObjectInfo:/app" -w /app php:8.3-cli `
  php -S 0.0.0.0:8080 -t public
```

Формат запроса:

```
GET /object_info.php?username=testuser&password=Summer2024!&user_token=TOKEN&Login=Login&id=2
```

Токен берётся из формы на странице. После входа пароль исчезает из URL,
остаётся `object_info.php?id=2`. Проверки:

```powershell
pip install -r requirements.txt
python tests/test_object_info.py
```

Все пять проверок должны завершиться `OK`: вход, вывод объекта, отказ при
SQL-инъекции в логине и в id, отказ без CSRF-токена.

## Ограничения

- SonarQube Community не содержит taint-анализа PHP, поэтому его 0 issues
  не означает отсутствия уязвимости. Это описано в отчёте.
- GET-формат с паролем сохранён по требованию задания. В реальной системе
  логин должен быть POST; остаточный риск CWE-598 указан явно.
- Все действия выполнялись только против DVWA на 127.0.0.1 и собственной
  страницы на 127.0.0.1. Внешние системы не использовались.

## Защита

**Перед ответом запускаю**

```powershell
cd "Практика5_Статический_анализ"
docker run -d --name dvwa-p5 -p 127.0.0.1:8081:80 vulnerables/web-dvwa
docker run --rm -v "${PWD}/SecureObjectInfo:/app" -w /app php:8.3-cli `
  php tools/seed_user.php testuser "Summer2024!" --reset
docker run -d --name p5-secure -p 127.0.0.1:8082:8080 `
  -v "${PWD}/SecureObjectInfo:/app" -w /app php:8.3-cli php -S 0.0.0.0:8080 -t public
python tests/test_object_info.py
```

Если контейнеры уже были, вместо `run` использую `start`; DVWA один раз инициализирую через `setup.php`.

**Порядок показа**

1. Запускаю Semgrep по `vulnerable/` и показываю два ERROR с CWE-89: `sqli/low.php:8` и `sqli_blind/low.php:8`.
2. Открываю `results/sqlmap_dump.log`: boolean-based blind, current database `dvwa`, строка `admin` с MD5-хэшем.
3. Открываю `burp/burp_history_selected_cropped.png`: в Burp `Proxy → HTTP history`, запросы с `1=1` (200) и `1=2` (404).
4. Запускаю `tests/test_object_info.py`: пять `OK`.
5. В браузере открываю `http://127.0.0.1:8082/object_info.php`, ввожу `testuser` / `Summer2024!`, показываю объект 2; в адресной строке после входа остаётся только `?id=2`.
6. Открываю `Отчет_Практика5.docx` — таблицы находок, CWE и проверок.

**Что говорю**

Semgrep нашёл именно то место, где `$_REQUEST['id']` попадает в строку SQL и уходит в `mysqli_query`. В blind-модуле результат не выводится, но разница 200/404 на условиях `1=1` и `1=2` даёт булев канал; sqlmap его подтвердил и вытащил администратора. Burp использовал как прокси: в HTTP history видно те же два запроса. SonarQube Community развернул, но у него нет taint-анализа PHP, поэтому его 0 issues — не доказательство; основной результат даёт Semgrep. Своя страница сохраняет GET-формат из задания, но использует PDO с параметрами, `password_hash`, CSRF и ограничение попыток; инъекция в логин и в `id` не проходит.

**Вопросы, к которым готовлюсь**

- Почему sqlmap сработал, хотя ошибки подавлены: boolean-based blind не требует текста ошибки, достаточно разницы ответов.
- Почему Burp, а не только curl: Burp показывает запрос, cookie и ответ в одном месте, удобно менять payload в Repeater.
- Почему SonarQube 0: в Community-сборке нет taint-правил для PHP; это ограничение инструмента, а не чистота кода.
- Почему пароль в GET: требование задания; остаточный риск CWE-598, в реальной системе — POST.
