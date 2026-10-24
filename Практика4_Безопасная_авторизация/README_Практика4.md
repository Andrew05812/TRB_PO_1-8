# Практика 4. Аутентификация и защита от перебора

Колесников А.Ю., БСБО-03-23, студ. билет 23Б0099

## Что в папке

- `bruteforce_dvwa.py` — переборщик формы входа DVWA (пункт 1 задания);
- `wordlist_p4.txt` — словарь из 30 паролей, пароль стенда — 20-й;
- `dvwa_results.csv`, `secure_results.csv` — результаты обоих запусков;
- `SecureAuthApp/` — своя система авторизации (пункт 3);
- `gen_report.py` — сборка отчёта из CSV;
- `Отчет_Практика4.docx` — готовый отчёт с код-ревью по CWE.

## Стенд DVWA

Проще всего поднять DVWA в Docker (версия 1.10, тот же модуль
`vulnerabilities/brute`, что и в Web Security Dojo):

```powershell
docker run -d --name dvwa-lab -p 8081:80 vulnerables/web-dvwa
```

После запуска открыть `http://127.0.0.1:8081/setup.php` и нажать
«Create / Reset Database». В этом стенде пароль администратора —
`Summer2024!` (в стандартном DVWA был бы `password`); он специально
добавлен в словарь, чтобы перебор был воспроизводимым.

Перебор на высоком уровне:

```powershell
python bruteforce_dvwa.py --url http://127.0.0.1:8081/vulnerabilities/brute/ --username admin --wordlist wordlist_p4.txt --login-url http://127.0.0.1:8081/login.php --login-username admin --login-password "Summer2024!" --security high --results dvwa_results.csv
```

Скрипт сам получает CSRF-токен перед каждой попыткой, поэтому уровень high
его не останавливает. Результат последнего запуска: пароль найден на
20-й попытке за 28,42 с.

## Своя система авторизации

Лежит в `SecureAuthApp`, запускается в PHP 8.3 (можно в Docker, если PHP
на хост не установлен). Подробная инструкция — в
`SecureAuthApp/README.md`. Кратко:

```powershell
docker run --rm -d --name secureauth-lab -p 127.0.0.1:8080:8080 -v "${PWD}/SecureAuthApp:/app" -w /app php:8.3-cli php -S 0.0.0.0:8080 -t public
docker exec secureauth-lab php tools/seed_user.php testuser "Summer2024!" --reset
```

Проверка тем же переборщиком:

```powershell
python bruteforce_dvwa.py --url http://127.0.0.1:8080/login.php --username testuser --wordlist wordlist_p4.txt --results secure_results.csv
```

Ожидаемый результат — `locked_out` на 6-й попытке: после пяти неудач
сервер отвечает 429 с `Retry-After`, и до пароля дело не доходит.

## Что именно защищает

- PDO с подготовленными выражениями вместо конкатенации SQL;
- `password_hash()`/`password_verify()` (bcrypt, cost 10) вместо MD5;
- блокировка по логину и IP: 5 неудач за 15 минут, ответ 429;
- задержка 1 секунда на каждую попытку;
- bcrypt от хэша-заглушки для несуществующего логина — одинаковое время ответа;
- CSRF-токен `user_token` во всех формах, выход только POST;
- `session_regenerate_id(true)` после входа, cookie HttpOnly/SameSite;
- защитные заголовки и отключённый вывод ошибок.

Формат входа оставлен GET с параметрами `username`, `password`,
`user_token`, `Login`, как требует пункт 3 задания. Пароль в URL — это
CWE-598 и единственный сознательно оставленный компромисс; в реальном
проекте форму нужно переводить на POST.

Подробный разбор уязвимостей DVWA по CWE, таблица проверок и выводы —
в `Отчет_Практика4.docx`.

## Защита

**Перед ответом запускаю**

```powershell
docker run -d --name dvwa-p4 -p 127.0.0.1:8081:80 vulnerables/web-dvwa
docker run -d --name p4-secure -p 127.0.0.1:8080:8080 `
  -v "${PWD}/SecureAuthApp:/app" -w /app php:8.3-cli php -S 0.0.0.0:8080 -t public
```

DVWA: вход `admin` / `password`, `Create / Reset Database`, `DVWA Security → low/high`. Перебор high уже сохранён в `dvwa_results.csv`; при необходимости запускаю `bruteforce_dvwa.py`, но это около 28 секунд.

**Порядок показа**

1. Открываю `bruteforce_dvwa.py`: на каждом шаге заново берётся `user_token`, поэтому high не останавливает перебор.
2. Показываю `dvwa_results.csv`: 20 попыток, пароль найден, 28,42 с.
3. Открываю `Отчет_Практика4.docx`, таблицу CWE: SQLi, MD5, отсутствие лимита, GET-пароль, XSS, cookie.
4. Запускаю свою форму на 8080: регистрирую/захожу, затем 5 раз неверный пароль — на следующей попытке 429 и `Retry-After`.
5. Проверяю `login.php` без `user_token` — отказ; с `username=' OR '1'='1` — отказ; logout GET — 405.

**Что говорю**

В DVWA на всех уровнях SQL собирается конкатенацией, а пароль хешируется MD5. `user_token` — это CSRF-токен, а не защита от перебора: скрипт сам заходит на страницу и получает новый токен перед каждой попыткой. На high добавляется `sleep(rand(0,3))`, поэтому 20 попыток идут 28 секунд, но всё равно доходят до пароля. В своей форме я убрал конкатенацию, перешёл на `password_hash`, добавил CSRF, ограничение попыток по логину и IP, задержку, смену session id и защитные заголовки. GET-формат с паролем оставлен по требованию задания, это CWE-598 и остаточный риск.

**Вопросы, к которым готовлюсь**

- Почему `mysqli_real_escape_string` не спасает: на medium запрос числовой, без кавычек, а экранирование рассчитано на строки.
- Почему блокировка по IP и по логину: распределённый перебор и подбор логинов с одного адреса — разные сценарии.
- Почему пароль в GET — плохо: история браузера, логи сервера, Referer; в реальной системе только POST.
- Почему `password_hash`, а не SHA-256: bcrypt медленный и с солью, это усложняет словарь и радужные таблицы.
