<?php
// Единая точка входа для всех страниц: настройка ошибок, заголовки
// безопасности и запуск сессии. Подключается первой строкой в public/*.php,
// чтобы ни одна страница не забыла выставить защитные заголовки.

declare(strict_types=1);

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/csrf.php';
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/rate_limit.php';

// Ошибки и предупреждения не показываем в браузер (CWE-209): клиенту
// незачем видеть пути к файлам, текст SQL и стек вызовов. В журнал PHP
// они по-прежнему попадают.
ini_set('display_errors', '0');
ini_set('display_startup_errors', '0');
ini_set('log_errors', '1');
error_reporting(E_ALL);

header('Content-Type: text/html; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header('Referrer-Policy: no-referrer');
header('Permissions-Policy: geolocation=(), microphone=(), camera=()');
// Скриптов на страницах нет вообще, поэтому script-src можно не разрешать.
// style-src 'self' - стили только из своих файлов (inline-стилей нет).
// frame-ancestors 'none' и X-Frame-Options запрещают встраивать форму в iframe.
header("Content-Security-Policy: default-src 'self'; img-src 'self' data:; "
    . "style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'");
header('Cache-Control: no-store, no-cache, must-revalidate');
header_remove('X-Powered-By');

// Любое необработанное исключение превращаем в общую страницу 500,
// а подробности пишем только в лог. Так наружу не утекут детали БД.
set_exception_handler(static function (Throwable $e): void {
    error_log('[SecureAuthApp] ' . $e->getMessage()
        . ' in ' . $e->getFile() . ':' . $e->getLine());
    if (!headers_sent()) {
        http_response_code(500);
        header('Content-Type: text/html; charset=utf-8');
    }
    echo '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        . '<title>Ошибка</title></head><body><h1>Внутренняя ошибка</h1>'
        . '<p>Попробуйте позже.</p></body></html>';
});

csrf_start_session();
