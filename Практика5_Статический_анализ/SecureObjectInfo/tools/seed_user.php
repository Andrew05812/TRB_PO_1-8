<?php
// Создание (или обновление) тестового пользователя из командной строки.
// Нужен, чтобы не регистрировать его каждый раз через браузер и чтобы
// удобно сбрасывать журнал попыток перед проверкой блокировки.
//
// Запуск:
//   php tools/seed_user.php testuser "Summer2024!"
//   php tools/seed_user.php testuser "Summer2024!" --reset
//
// --reset очищает login_attempts целиком. Это допустимо только на локальном
// учебном стенде: на реальной системе журнал попыток входа стирать нельзя.

declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}

require_once __DIR__ . '/../src/config.php';
require_once __DIR__ . '/../src/db.php';

if ($argc < 3) {
    fwrite(STDERR, "Использование: php tools/seed_user.php USER PASS [--reset]\n");
    exit(2);
}

$username = trim($argv[1]);
$password = $argv[2];
$reset = in_array('--reset', $argv, true);

if (!preg_match('/^[\p{L}\p{N}_.-]{3,50}$/u', $username)) {
    fwrite(STDERR, "Логин: от 3 до 50 символов, буквы, цифры, точка, дефис или подчёркивание.\n");
    exit(2);
}
if (mb_strlen($password) < MIN_PASSWORD_LENGTH) {
    fwrite(STDERR, "Пароль должен быть не короче " . MIN_PASSWORD_LENGTH . " символов.\n");
    exit(2);
}
if (strlen($password) > MAX_PASSWORD_BYTES) {
    fwrite(STDERR, "Пароль не должен быть длиннее " . MAX_PASSWORD_BYTES . " байт.\n");
    exit(2);
}

$pdo = get_db();
$hash = password_hash($password, PASSWORD_DEFAULT);

$stmt = $pdo->prepare('SELECT id FROM users WHERE username = :u');
$stmt->execute([':u' => $username]);
$id = $stmt->fetchColumn();

if ($id) {
    $upd = $pdo->prepare('UPDATE users SET password_hash = :h WHERE id = :id');
    $upd->execute([':h' => $hash, ':id' => $id]);
    echo "Пользователь {$username} обновлён (id={$id}).\n";
} else {
    $ins = $pdo->prepare('INSERT INTO users (username, password_hash) VALUES (:u, :h)');
    $ins->execute([':u' => $username, ':h' => $hash]);
    echo "Пользователь {$username} создан (id=" . $pdo->lastInsertId() . ").\n";
}

if ($reset) {
    $pdo->exec('DELETE FROM login_attempts');
    echo "Журнал попыток входа очищен.\n";
}
