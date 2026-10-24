# SecureObjectInfo — защищённая страница вывода объекта (Практика 5)

Основа взята из приложения практики 4 (авторизация), добавлена страница
`object_info.php`, которая выводит объект по `id`. Формат запроса сохранён как
в задании:

```
GET /object_info.php?username=USER&password=PASS&user_token=TOKEN&Login=Login&id=1
```

Из-за GET пароль остаётся в URL — это требование задания, остаточный риск
CWE-598 разобран в отчёте. В реальной системе логин должен быть POST.

## Запуск

```powershell
docker run --rm -v "${PWD}:/app" -w /app php:8.3-cli `
  php tools/seed_user.php testuser "Summer2024!" --reset
docker run -d --name p5-secure -p 127.0.0.1:8082:8080 `
  -v "${PWD}:/app" -w /app php:8.3-cli php -S 0.0.0.0:8080 -t public
```

Открыть `http://127.0.0.1:8082/object_info.php`. Пользователь `testuser`,
пароль `Summer2024!`, объекты 1–3 создаются схемой автоматически.

## Что защищено

- логин и пароль проверяются подготовленным запросом PDO;
- пароль хранится через `password_hash()`, а не MD5;
- `id` приводится к целому через `FILTER_VALIDATE_INT` и всё равно передаётся
  параметром `:id`;
- CSRF-токен `user_token` обязателен, сравнение через `hash_equals`;
- после успешного входа `session_regenerate_id(true)`, пароль убирается из URL
  редиректом на `object_info.php?id=N`;
- после 5 неудач за 15 минут блокируются логин и IP, отдаётся 429 с
  `Retry-After`;
- вывод экранируется `htmlspecialchars`;
- ошибки не показываются в браузер, только пишутся в лог.

## Проверка

```powershell
python ../tests/test_object_info.py
```

Пять проверок: вход, вывод объекта, отказ при инъекции в логине, отказ при
инъекции в `id`, отказ без CSRF-токена. Все должны завершиться `OK`.
