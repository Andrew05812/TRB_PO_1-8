<?php
// Защита от перебора паролей (CWE-307: Improper Restriction of Excessive
// Authentication Attempts). Именно отсутствие этой проверки в задании
// bruteforce DVWA и позволяет переборщику работать без каких-либо помех.
//
// Блокируем по двум ключам одновременно - по имени пользователя и по IP:
//   - блокировка по username защищает конкретный аккаунт, даже если
//     запросы идут с разных IP (распределённый перебор/ботнет);
//   - блокировка по IP защищает от перебора по словарю логинов с одного места,
//     даже если атакующий каждый раз угадывает ровно одну попытку на логин.

declare(strict_types=1);
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/config.php';

function get_client_ip(): string
{
    // В реальном проде IP нужно брать с учётом доверенного прокси/балансировщика
    // (X-Forwarded-For от ненадёжного источника подделать как раз элементарно)
    return $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
}

function count_recent_failed_attempts(PDO $pdo, string $key, string $column): int
{
    // $column - не пользовательский ввод, а одна из двух захардкоженных
    // строк ('username' или 'ip_address'), поэтому подстановка в текст
    // запроса безопасна; сам ключ (username/ip) идёт только через bindValue.
    if (!in_array($column, ['username', 'ip_address'], true)) {
        throw new InvalidArgumentException('Недопустимая колонка для rate limit');
    }

    $stmt = $pdo->prepare(
        "SELECT COUNT(*) FROM login_attempts
         WHERE $column = :key
           AND success = 0
           AND attempted_at >= datetime('now', :window)"
    );
    $stmt->bindValue(':key', $key, PDO::PARAM_STR);
    $stmt->bindValue(':window', '-' . LOCKOUT_WINDOW_SECONDS . ' seconds', PDO::PARAM_STR);
    $stmt->execute();
    return (int)$stmt->fetchColumn();
}

/**
 * Сколько секунд осталось до конца блокировки по одному ключу.
 * Логика такая: если неудачных попыток уже MAX_FAILED_ATTEMPTS, то
 * блокировка снимется, когда самая старая из этих попыток выйдет за окно.
 * Для этого берём MAX_FAILED_ATTEMPTS-ю с конца запись и прибавляем окно.
 */
function lockout_seconds_for_key(PDO $pdo, string $key, string $column): int
{
    if (!in_array($column, ['username', 'ip_address'], true)) {
        throw new InvalidArgumentException('Недопустимая колонка для rate limit');
    }

    $stmt = $pdo->prepare(
        "SELECT attempted_at FROM login_attempts
         WHERE $column = :key
           AND success = 0
           AND attempted_at >= datetime('now', :window)
         ORDER BY attempted_at DESC, id DESC
         LIMIT 1 OFFSET :offset"
    );
    $stmt->bindValue(':key', $key, PDO::PARAM_STR);
    $stmt->bindValue(':window', '-' . LOCKOUT_WINDOW_SECONDS . ' seconds', PDO::PARAM_STR);
    $stmt->bindValue(':offset', MAX_FAILED_ATTEMPTS - 1, PDO::PARAM_INT);
    $stmt->execute();
    $row = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$row) {
        return 0;
    }

    // SQLite datetime('now') отдаёт UTC без суффикса, поэтому читаем
    // строку именно как UTC, а не как локальное время.
    $attempt = new DateTimeImmutable($row['attempted_at'], new DateTimeZone('UTC'));
    $unlockAt = $attempt->getTimestamp() + LOCKOUT_WINDOW_SECONDS;
    return max(0, $unlockAt - time());
}

/**
 * Возвращает максимум из блокировок по логину и по IP: если заблокирован
 * хотя бы один ключ, вход запрещён, пока не истечёт более длинная блокировка.
 */
function lockout_seconds_remaining(PDO $pdo, string $username, string $ip): int
{
    return max(
        lockout_seconds_for_key($pdo, $username, 'username'),
        lockout_seconds_for_key($pdo, $ip, 'ip_address')
    );
}

function is_locked_out(PDO $pdo, string $username, string $ip): bool
{
    return lockout_seconds_remaining($pdo, $username, $ip) > 0;
}

function record_attempt(PDO $pdo, string $username, string $ip, bool $success): void
{
    $stmt = $pdo->prepare(
        'INSERT INTO login_attempts (username, ip_address, success) VALUES (:u, :ip, :s)'
    );
    $stmt->execute([
        ':u' => $username,
        ':ip' => $ip,
        ':s' => $success ? 1 : 0,
    ]);
}
