<?php
declare(strict_types=1);
require_once __DIR__ . '/../src/bootstrap.php';

$error = null;
$success = null;
$username = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    // Регистрация - через POST (в отличие от логина, тут совместимость
    // с форматом GET из задания bruteforce не требуется, поэтому пароль
    // ни разу не попадает ни в URL, ни в логи веб-сервера)
    if (!csrf_check($_POST['user_token'] ?? null)) {
        $error = 'Сессия устарела, обновите страницу и попробуйте снова.';
    } else {
        $username = trim((string)($_POST['username'] ?? ''));
        $password = (string)($_POST['password'] ?? '');
        $password2 = (string)($_POST['password2'] ?? '');

        // Логин: буквы (включая кириллицу), цифры, точка, дефис и
        // подчёркивание. Пробелы и угловые скобки не разрешаем, чтобы
        // не плодить имена, которые потом придётся экранировать в каждом
        // месте вывода. Длину считаем в символах, а не в байтах.
        if (!preg_match('/^[\p{L}\p{N}_.-]{3,50}$/u', $username)) {
            $error = 'Логин: от 3 до 50 символов, буквы, цифры, точка, дефис или подчёркивание.';
        } elseif (mb_strlen($password) < MIN_PASSWORD_LENGTH) {
            $error = 'Пароль должен быть не короче ' . MIN_PASSWORD_LENGTH . ' символов.';
        } elseif (strlen($password) > MAX_PASSWORD_BYTES) {
            // Ограничение именно в байтах: bcrypt всё равно обрежет всё,
            // что длиннее 72 байт, поэтому лучше сказать об этом сразу.
            $error = 'Пароль не должен быть длиннее ' . MAX_PASSWORD_BYTES . ' байт.';
        } elseif ($password !== $password2) {
            $error = 'Пароли не совпадают.';
        } else {
            $pdo = get_db();

            try {
                // password_hash() сам генерирует случайную соль и сам выбирает
                // безопасный алгоритм (по умолчанию bcrypt) - в отличие от md5()
                // из исходного уязвимого кода (CWE-327 / CWE-916)
                $hash = password_hash($password, PASSWORD_DEFAULT);
                $stmt = $pdo->prepare('INSERT INTO users (username, password_hash) VALUES (:u, :h)');
                $stmt->execute([':u' => $username, ':h' => $hash]);
                $success = 'Готово, теперь можно войти.';
                $username = '';
            } catch (PDOException $e) {
                // UNIQUE-ограничение в SQLite даёт SQLSTATE 23000. Проверка
                // "сначала SELECT, потом INSERT" без транзакции оставляет
                // окно для гонки, поэтому окончательно решает база.
                if ($e->getCode() === '23000') {
                    $error = 'Такой пользователь уже существует.';
                } else {
                    throw $e;
                }
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
    <title>Регистрация</title>
</head>
<body>
<h1>Регистрация</h1>

<?php if ($error): ?>
    <p><b>Ошибка:</b> <?= htmlspecialchars($error, ENT_QUOTES, 'UTF-8') ?></p>
<?php endif; ?>
<?php if ($success): ?>
    <p><?= htmlspecialchars($success, ENT_QUOTES, 'UTF-8') ?> <a href="login.php">Войти</a></p>
<?php endif; ?>

<form method="post" action="register.php">
    <input type="hidden" name="user_token" value="<?= htmlspecialchars($token, ENT_QUOTES, 'UTF-8') ?>">
    <p><label>Логин: <input type="text" name="username" maxlength="50"
        value="<?= htmlspecialchars($username, ENT_QUOTES, 'UTF-8') ?>"
        autocomplete="username" required></label></p>
    <p><label>Пароль: <input type="password" name="password" minlength="8" maxlength="72"
        autocomplete="new-password" required></label></p>
    <p><label>Пароль ещё раз: <input type="password" name="password2" minlength="8" maxlength="72"
        autocomplete="new-password" required></label></p>
    <p><button type="submit">Зарегистрироваться</button></p>
</form>

<p><a href="login.php">Уже есть аккаунт</a></p>

</body>
</html>
