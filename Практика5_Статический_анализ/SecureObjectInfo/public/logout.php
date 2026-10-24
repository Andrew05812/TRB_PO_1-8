<?php
declare(strict_types=1);
require_once __DIR__ . '/../src/bootstrap.php';

// Выход только POST-запросом с токеном. GET-ссылка на logout позволяла бы
// любому сайту разлогинить пользователя (частный случай CSRF).
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    header('Allow: POST');
    echo '<p>Для выхода используйте кнопку на странице кабинета.</p>';
    exit;
}

if (!csrf_check($_POST['user_token'] ?? null)) {
    http_response_code(403);
    echo '<p>Неверный CSRF-токен. Выход отменён.</p>';
    exit;
}

$_SESSION = [];

if (ini_get('session.use_cookies')) {
    $params = session_get_cookie_params();
    setcookie(session_name(), '', [
        'expires' => time() - 42000,
        'path' => $params['path'],
        'domain' => $params['domain'],
        'secure' => $params['secure'],
        'httponly' => $params['httponly'],
        'samesite' => $params['samesite'] ?? 'Lax',
    ]);
}

session_destroy();

header('Location: login.php', true, 302);
exit;
