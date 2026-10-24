-- Схема БД для защищённой системы авторизации.
-- SQLite выбран ради простоты запуска (не нужен отдельный сервер БД) -
-- для MySQL (как в оригинальном dvwa) синтаксис почти такой же, отличия
-- отмечены комментариями рядом.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT, -- в MySQL: INT AUTO_INCREMENT PRIMARY KEY
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,                      -- результат password_hash(), НЕ md5()
    avatar        TEXT DEFAULT '/assets/default_avatar.png',
    created_at    TEXT DEFAULT (datetime('now'))
);

-- Журнал попыток входа - на нём построена защита от перебора (CWE-307).
-- Пишем каждую попытку, успешную и нет, с IP и временем.
CREATE TABLE IF NOT EXISTS login_attempts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL,
    ip_address   TEXT NOT NULL,
    success      INTEGER NOT NULL,   -- 0/1, в MySQL можно TINYINT(1)
    attempted_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_attempts_username_time ON login_attempts(username, attempted_at);
CREATE INDEX IF NOT EXISTS idx_attempts_ip_time ON login_attempts(ip_address, attempted_at);

-- Объекты, которые выводит защищённая страница object_info.php.
-- Поле secret намеренно выглядит как «интересные данные»: если бы запрос
-- был уязвим к SQL-инъекции, через UNION можно было бы вытащить сюда
-- password_hash из users. Именно это и проверяется в тестах.
CREATE TABLE IF NOT EXISTS objects (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    owner   TEXT NOT NULL,
    secret  TEXT NOT NULL
);

INSERT OR IGNORE INTO objects (id, name, owner, secret) VALUES
    (1, 'Договор поставки', 'ivanov', 'внутренний идентификатор 1001'),
    (2, 'Счёт за сентябрь', 'petrov', 'внутренний идентификатор 1002'),
    (3, 'Акт приёмки', 'sidorov', 'внутренний идентификатор 1003');
