<?php
declare(strict_types=1);
require_once __DIR__ . '/../src/bootstrap.php';

// Страница вывода информации об объекте. Формат запроса оставлен таким же,
// как в задании:
//   object_info.php?username=USER&password=PASS&user_token=TOKEN&Login=Login&id=1
// Это сделано специально, чтобы старый переборщик и sqlmap можно было
// направить на неё без переделки запросов. Отличие от DVWA в том, что здесь
// нет ни конкатенации SQL, ни md5(), ни доступа к чужим объектам по id.

$html = '';
$username = '';
$object = null;
$objectId = filter_input(INPUT_GET, 'id', FILTER_VALIDATE_INT);
if ($objectId === false || $objectId === null || $objectId < 1) {
    $objectId = 1;
}

$pdo = get_db();

// Если пользователь уже вошёл через login.php, повторно спрашивать пароль
// не нужно. Ветка с GET-параметрами нужна для совместимости с заданием.
if (empty($_SESSION['user_id']) && isset($_GET['Login'])) {
    $username = trim((string)($_GET['username'] ?? ''));
    $password = (string)($_GET['password'] ?? '');
    $token = $_GET['user_token'] ?? null;

    if (!csrf_check($token)) {
        $html = '<p>Сессия устарела или запрос отправлен не с этой страницы. Обновите страницу.</p>';
    } elseif ($username === '' || mb_strlen($username) > USERNAME_MAX_LENGTH
        || strlen($password) > MAX_PASSWORD_BYTES) {
        record_attempt($pdo, mb_substr($username, 0, USERNAME_MAX_LENGTH), get_client_ip(), false);
        $html = '<pre>Username and/or password incorrect.</pre>';
    } else {
        $ip = get_client_ip();
        $remaining = lockout_seconds_remaining($pdo, $username, $ip);

        if ($remaining > 0) {
            http_response_code(429);
            header('Retry-After: ' . $remaining);
            $html = '<p>Слишком много неудачных попыток входа. Попробуйте позже.</p>';
        } else {
            usleep(LOGIN_THROTTLE_SECONDS * 1_000_000);

            // Параметры передаются в запрос отдельно от текста SQL. Даже
            // строка "1' OR '1'='1" будет воспринята как обычное значение
            // username, а не как часть SQL-выражения.
            $stmt = $pdo->prepare('SELECT id, password_hash FROM users WHERE username = :u');
            $stmt->execute([':u' => $username]);
            $row = $stmt->fetch(PDO::FETCH_ASSOC);

            $hash = $row ? $row['password_hash'] : DUMMY_PASSWORD_HASH;
            $ok = password_verify($password, $hash);

            if ($row && $ok) {
                record_attempt($pdo, $username, $ip, true);
                session_regenerate_id(true);
                $_SESSION['user_id'] = (int)$row['id'];
                $_SESSION['username'] = $username;

                // После успешного входа убираем пароль из адресной строки:
                // redirect на тот же объект без username/password.
                header('Location: object_info.php?id=' . $objectId, true, 302);
                exit;
            }

            record_attempt($pdo, $username, $ip, false);
            $html = '<pre>Username and/or password incorrect.</pre>';
        }
    }
}

if (!empty($_SESSION['user_id'])) {
    // Единственное место, где id попадает в SQL - параметр :id. Приведение
    // к int уже сделано выше через FILTER_VALIDATE_INT, но prepared statement
    // всё равно обязателен: так правило работает независимо от типа поля.
    $stmt = $pdo->prepare(
        'SELECT id, name, owner, secret FROM objects WHERE id = :id'
    );
    $stmt->bindValue(':id', $objectId, PDO::PARAM_INT);
    $stmt->execute();
    $object = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$object) {
        $html = '<p>Объект с таким номером не найден.</p>';
    }
}

$token = csrf_get_token();
?>
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="referrer" content="no-referrer">
    <title>Информация об объекте</title>
</head>
<body>
<h1>Информация об объекте</h1>

<?= $html ?>

<?php if ($object): ?>
    <table border="1" cellpadding="4">
        <tr><th>Номер</th><td><?= (int)$object['id'] ?></td></tr>
        <tr><th>Название</th><td><?= htmlspecialchars($object['name'], ENT_QUOTES, 'UTF-8') ?></td></tr>
        <tr><th>Владелец</th><td><?= htmlspecialchars($object['owner'], ENT_QUOTES, 'UTF-8') ?></td></tr>
        <tr><th>Служебные данные</th><td><?= htmlspecialchars($object['secret'], ENT_QUOTES, 'UTF-8') ?></td></tr>
    </table>
    <p><a href="object_info.php?id=<?= $objectId + 1 ?>">Следующий объект</a></p>
<?php endif; ?>

<?php if (empty($_SESSION['user_id'])): ?>
    <h2>Вход</h2>
    <form method="get" action="object_info.php">
        <input type="hidden" name="user_token" value="<?= htmlspecialchars($token, ENT_QUOTES, 'UTF-8') ?>">
        <input type="hidden" name="id" value="<?= $objectId ?>">
        <p><label>Логин: <input type="text" name="username" maxlength="50"
            value="<?= htmlspecialchars($username, ENT_QUOTES, 'UTF-8') ?>"
            autocomplete="username" required></label></p>
        <p><label>Пароль: <input type="password" name="password" maxlength="72"
            autocomplete="current-password" required></label></p>
        <p><button type="submit" name="Login" value="Login">Войти и открыть объект</button></p>
    </form>
    <p><a href="register.php">Зарегистрироваться</a></p>
<?php else: ?>
    <p>Вы вошли как <?= htmlspecialchars((string)$_SESSION['username'], ENT_QUOTES, 'UTF-8') ?>.</p>
    <form method="post" action="logout.php">
        <input type="hidden" name="user_token" value="<?= htmlspecialchars($token, ENT_QUOTES, 'UTF-8') ?>">
        <button type="submit">Выйти</button>
    </form>
<?php endif; ?>
</body>
</html>
