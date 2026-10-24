<?php
// CSRF-токен (в оригинальном DVWA он называется user_token - оставляю то же
// имя параметра, чтобы форма входа осталась совместимой с форматом запроса
// из задания: ?username=...&password=...&user_token=...&Login=Login).
//
// В исходном уязвимом коде из методички (низкий уровень защиты DVWA)
// токена не было вообще - его можно было обойти просто не передавая
// параметр. Здесь токен обязателен и проверяется до обращения к БД.

declare(strict_types=1);

function csrf_start_session(): void
{
    if (session_status() === PHP_SESSION_ACTIVE) {
        return;
    }

    // Имя сессии по умолчанию PHPSESSID слишком узнаваемо и совпадает
    // с другими приложениями на том же хосте - задаём своё.
    session_name('SECUREAUTHSESSID');

    // false - cookie не должна читаться из JavaScript (защита от кражи
    // сессии через XSS); samesite=Lax - браузер не отправит её при
    // переходе со стороннего сайта (дополнительная защита от CSRF).
    $https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
        || (($_SERVER['SERVER_PORT'] ?? '') === '443');

    session_set_cookie_params([
        'lifetime' => 0,
        'path' => '/',
        'domain' => '',
        'secure' => $https,   // под HTTPS cookie уходит только по HTTPS
        'httponly' => true,
        'samesite' => 'Lax',
    ]);

    // use_strict_mode не даёт подсунуть произвольный session id, которого
    // сервер не выдавал. use_only_cookies запрещает передавать id в URL.
    ini_set('session.use_strict_mode', '1');
    ini_set('session.use_only_cookies', '1');

    session_start();
}

function csrf_get_token(): string
{
    csrf_start_session();
    if (empty($_SESSION['user_token'])) {
        $_SESSION['user_token'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['user_token'];
}

function csrf_check(mixed $submittedToken): bool
{
    csrf_start_session();
    // Параметр приходит извне, поэтому доверять его типу нельзя: запрос
    // вида user_token[]=... даст массив, а не строку. Явно проверяем тип,
    // иначе hash_equals() упадёт с TypeError и вернёт 500 вместо отказа.
    if (empty($_SESSION['user_token']) || !is_string($submittedToken) || $submittedToken === '') {
        return false;
    }
    // hash_equals - сравнение за постоянное время, а не обычным ==,
    // чтобы нельзя было угадать токен по разнице во времени ответа
    return hash_equals($_SESSION['user_token'], $submittedToken);
}
