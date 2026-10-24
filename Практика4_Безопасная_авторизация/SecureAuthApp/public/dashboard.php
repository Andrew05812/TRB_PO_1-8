<?php
declare(strict_types=1);
require_once __DIR__ . '/../src/bootstrap.php';

if (empty($_SESSION['user_id'])) {
    header('Location: login.php', true, 302);
    exit;
}

$username = (string)($_SESSION['username'] ?? '');
$token = csrf_get_token();
?>
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="referrer" content="no-referrer">
    <title>Личный кабинет</title>
</head>
<body>
<!-- htmlspecialchars обязателен: имя пользователя - это данные,
     которые когда-то ввёл сам пользователь, выводить их в HTML
     без экранирования - верный способ словить отражённый XSS -->
<h1>Добро пожаловать, <?= htmlspecialchars($username, ENT_QUOTES, 'UTF-8') ?>!</h1>
<p>Это защищённая страница. Она доступна только после успешного входа.</p>

<!-- Выход сделан POST-запросом с CSRF-токеном: иначе достаточно было бы
     заставить пользователя открыть ссылку logout.php, чтобы разлогинить его -->
<form method="post" action="logout.php">
    <input type="hidden" name="user_token" value="<?= htmlspecialchars($token, ENT_QUOTES, 'UTF-8') ?>">
    <button type="submit">Выйти</button>
</form>
</body>
</html>
