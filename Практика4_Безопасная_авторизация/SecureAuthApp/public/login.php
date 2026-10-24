<?php
declare(strict_types=1);
require_once __DIR__ . '/../src/bootstrap.php';

// Формат запроса намеренно оставлен таким же, как в задании bruteforce dvwa:
// GET /login.php?username=USER&password=PASS&user_token=TOKEN&Login=Login
// (пункт 3 задания прямо требует совместимости с этим форматом) -
// но, в отличие от оригинала, здесь это не делает форму менее безопасной:
// пароль всё ещё можно перехватить из истории браузера/логов сервера,
// это единственная уступка, продиктованная требованиями задания, и она
// явно отмечена как остаточный риск в отчёте (раздел про CWE-598).

$html = '';
$username = '';
$ip = get_client_ip();

if (isset($_GET['Login'])) {
    $username = trim((string)($_GET['username'] ?? ''));
    $password = (string)($_GET['password'] ?? '');
    $token = $_GET['user_token'] ?? null;

    if (!csrf_check($token)) {
        $html = '<p>Сессия устарела или запрос отправлен не с этой страницы. Обновите страницу.</p>';
    } else {
        $pdo = get_db();

        // Слишком длинный логин или пароль отсекаем до базы. Для пароля
        // это принципиально: bcrypt смотрит только первые 72 байта, и без
        // проверки два разных длинных пароля могли бы считаться одинаковыми.
        if ($username === '' || mb_strlen($username) > USERNAME_MAX_LENGTH
            || strlen($password) > MAX_PASSWORD_BYTES) {
            record_attempt($pdo, mb_substr($username, 0, USERNAME_MAX_LENGTH), $ip, false);
            $html = '<pre>Username and/or password incorrect.</pre>';
        } else {
            $remaining = lockout_seconds_remaining($pdo, $username, $ip);

            if ($remaining > 0) {
                // 429 Too Many Requests + Retry-After: честный машинный
                // ответ, по которому и браузер, и переборщик понимают,
                // что попытки временно запрещены.
                http_response_code(429);
                header('Retry-After: ' . $remaining);
                $html = '<p>Слишком много неудачных попыток входа. Попробуйте позже.</p>';
            } else {
                // Небольшая задержка на каждую попытку - без неё даже с лимитом
                // в 5 попыток/15 минут перебор можно пытаться запускать
                // параллельно с разных соединений быстрее, чем блокировка успеет
                // сработать
                usleep(LOGIN_THROTTLE_SECONDS * 1_000_000);

                $stmt = $pdo->prepare('SELECT id, password_hash FROM users WHERE username = :u');
                $stmt->execute([':u' => $username]);
                $row = $stmt->fetch(PDO::FETCH_ASSOC);

                // Если логина нет, всё равно считаем bcrypt от хэша-заглушки.
                // Иначе ответ для несуществующего пользователя возвращался бы
                // заметно быстрее, и по времени можно было бы перебирать логины.
                $hash = $row ? $row['password_hash'] : DUMMY_PASSWORD_HASH;
                $ok = password_verify($password, $hash);

                if ($row && $ok) {
                    record_attempt($pdo, $username, $ip, true);

                    // Если в будущем cost или алгоритм по умолчанию изменятся,
                    // старый хэш можно будет обновить прямо при входе.
                    if (password_needs_rehash($row['password_hash'], PASSWORD_DEFAULT)) {
                        $newHash = password_hash($password, PASSWORD_DEFAULT);
                        $upd = $pdo->prepare('UPDATE users SET password_hash = :h WHERE id = :id');
                        $upd->execute([':h' => $newHash, ':id' => $row['id']]);
                    }

                    // Обязательно меняем id сессии после успешного входа -
                    // иначе возможна session fixation (CWE-384): если атакующий
                    // подсунул жертве cookie со своим session id заранее,
                    // после логина сессия осталась бы той же самой
                    session_regenerate_id(true);
                    $_SESSION['user_id'] = (int)$row['id'];
                    $_SESSION['username'] = $username;

                    header('Location: dashboard.php', true, 302);
                    exit;
                }

                record_attempt($pdo, $username, $ip, false);

                // Одно и то же сообщение независимо от того, не существует ли
                // такого логина или просто неверный пароль - чтобы по тексту
                // ошибки нельзя было проверять, какие логины вообще существуют
                $html = '<pre>Username and/or password incorrect.</pre>';
            }
        }
    }
}

$token = csrf_get_token();
?>
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="referrer" content="no-referrer">
    <title>Вход</title>
</head>
<body>
<h1>Вход</h1>

<?= $html ?>

<form method="get" action="login.php">
    <input type="hidden" name="user_token" value="<?= htmlspecialchars($token, ENT_QUOTES, 'UTF-8') ?>">
    <p><label>Логин: <input type="text" name="username" maxlength="50"
        value="<?= htmlspecialchars($username, ENT_QUOTES, 'UTF-8') ?>"
        autocomplete="username" required></label></p>
    <p><label>Пароль: <input type="password" name="password" maxlength="72"
        autocomplete="current-password" required></label></p>
    <p><button type="submit" name="Login" value="Login">Войти</button></p>
</form>

<p><a href="register.php">Зарегистрироваться</a></p>

</body>
</html>
