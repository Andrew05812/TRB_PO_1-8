<?php
// Подключение к БД через PDO. Главное, ради чего это обёрнуто в функцию -
// PDO с параметризованными запросами сам по себе закрывает SQL-инъекцию
// (CWE-89) - в отличие от исходного кода из задания, где логин и пароль
// подставлялись в SQL прямой конкатенацией строк.

declare(strict_types=1);
require_once __DIR__ . '/config.php';

function get_db(): PDO
{
    static $pdo = null;
    if ($pdo !== null) {
        return $pdo;
    }

    $dataDir = dirname(DB_FILE);
    if (!is_dir($dataDir)) {
        mkdir($dataDir, 0770, true);
    }

    $isNew = !file_exists(DB_FILE);

    $pdo = new PDO('sqlite:' . DB_FILE);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    // эмуляцию подготовленных запросов отключаем - пусть драйвер реально
    // присылает параметры отдельно от текста запроса, а не просто
    // экранирует их на стороне PHP
    $pdo->setAttribute(PDO::ATTR_EMULATE_PREPARES, false);

    if ($isNew) {
        $schema = file_get_contents(SCHEMA_FILE);
        $pdo->exec($schema);
    }

    return $pdo;
}
