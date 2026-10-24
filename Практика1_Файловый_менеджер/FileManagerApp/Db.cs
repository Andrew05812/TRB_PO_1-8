using System;
using System.Collections.Generic;

namespace FileManagerApp
{
    // Обёртка повыше уровнем над SqliteNative: открываем файл БД один раз
    // при старте программы, а дальше просто вызываем ExecuteNonQuery / Query.
    // Все запросы идут только через параметры (?), сам текст запроса
    // с данными пользователя никогда не склеивается - это и есть защита
    // от SQL-инъекций, про которую говорится в задании.
    internal class Db : IDisposable
    {
        private IntPtr _handle;

        public Db(string path)
        {
            int rc = SqliteNative.sqlite3_open(path, out _handle);
            if (rc != SqliteNative.SQLITE_OK)
                throw new Exception("Не удалось открыть файл БД: " + path);

            // Если два экземпляра программы одновременно пишут в одну БД,
            // второй будет ждать освобождения блокировки до 5 секунд, а не
            // падать сразу с "database is locked".
            ExecuteNonQuery("PRAGMA busy_timeout = 5000;");

            // Внешние ключи в SQLite по умолчанию выключены. Включаем, чтобы
            // Operations.file_id действительно ссылался на существующий файл.
            ExecuteNonQuery("PRAGMA foreign_keys = ON;");

            EnsureSchema();
        }

        // Создаёт таблицы, если их ещё нет. IF NOT EXISTS - чтобы программу
        // можно было запускать повторно и не падать на второй раз.
        private void EnsureSchema()
        {
            ExecuteNonQuery(@"
                CREATE TABLE IF NOT EXISTS Users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );");

            ExecuteNonQuery(@"
                CREATE TABLE IF NOT EXISTS Files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    size INTEGER,
                    location TEXT,
                    owner_id INTEGER,
                    FOREIGN KEY (owner_id) REFERENCES Users(id)
                );");

            ExecuteNonQuery(@"
                CREATE TABLE IF NOT EXISTS Operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    op_time TEXT DEFAULT (datetime('now')),
                    operation_type TEXT NOT NULL,
                    file_id INTEGER,
                    user_id INTEGER,
                    details TEXT,
                    FOREIGN KEY (file_id) REFERENCES Files(id),
                    FOREIGN KEY (user_id) REFERENCES Users(id)
                );");
        }

        public void ExecuteNonQuery(string sql, params object[] args)
        {
            IntPtr stmt = Prepare(sql, args);
            int rc = SqliteNative.sqlite3_step(stmt);
            if (rc != SqliteNative.SQLITE_DONE && rc != SqliteNative.SQLITE_ROW)
            {
                string msg = SqliteNative.PtrToUtf8String(SqliteNative.sqlite3_errmsg(_handle));
                SqliteNative.sqlite3_finalize(stmt);
                throw new Exception("Ошибка SQL-запроса: " + msg);
            }
            SqliteNative.sqlite3_finalize(stmt);
        }

        // после INSERT удобно сразу узнать id новой строки
        public long ExecuteInsert(string sql, params object[] args)
        {
            ExecuteNonQuery(sql, args);
            return SqliteNative.sqlite3_last_insert_rowid(_handle);
        }

        public List<Dictionary<string, object>> Query(string sql, params object[] args)
        {
            var result = new List<Dictionary<string, object>>();
            IntPtr stmt = Prepare(sql, args);
            int colCount = SqliteNative.sqlite3_column_count(stmt);

            int rc;
            while ((rc = SqliteNative.sqlite3_step(stmt)) == SqliteNative.SQLITE_ROW)
            {
                var row = new Dictionary<string, object>();
                for (int i = 0; i < colCount; i++)
                {
                    string colName = SqliteNative.PtrToUtf8String(SqliteNative.sqlite3_column_name(stmt, i));
                    int type = SqliteNative.sqlite3_column_type(stmt, i);

                    object value;
                    if (type == SqliteNative.SQLITE_NULL)
                        value = null;
                    else if (type == SqliteNative.SQLITE_INTEGER)
                        value = SqliteNative.sqlite3_column_int64(stmt, i);
                    else
                        value = SqliteNative.PtrToUtf8String(SqliteNative.sqlite3_column_text(stmt, i));

                    row[colName] = value;
                }
                result.Add(row);
            }

            // Раньше ошибка выполнения запроса молча возвращала пустой/неполный
            // результат. Теперь её видно сразу, а не через полчаса отладки.
            if (rc != SqliteNative.SQLITE_DONE)
            {
                string msg = SqliteNative.PtrToUtf8String(SqliteNative.sqlite3_errmsg(_handle));
                SqliteNative.sqlite3_finalize(stmt);
                throw new Exception("Ошибка чтения из БД: " + msg);
            }

            SqliteNative.sqlite3_finalize(stmt);
            return result;
        }

        private IntPtr Prepare(string sql, object[] args)
        {
            byte[] sqlBytes = SqliteNative.ToUtf8Z(sql);
            int rc = SqliteNative.sqlite3_prepare_v2(_handle, sqlBytes, sqlBytes.Length, out IntPtr stmt, IntPtr.Zero);
            if (rc != SqliteNative.SQLITE_OK)
                throw new Exception("Не смог разобрать SQL: " + SqliteNative.PtrToUtf8String(SqliteNative.sqlite3_errmsg(_handle)));

            for (int i = 0; i < args.Length; i++)
            {
                int idx = i + 1; // в sqlite параметры нумеруются с единицы, а не с нуля
                int bindResult;

                if (args[i] == null)
                {
                    bindResult = SqliteNative.sqlite3_bind_null(stmt, idx);
                }
                else if (args[i] is int intVal)
                {
                    bindResult = SqliteNative.sqlite3_bind_int64(stmt, idx, intVal);
                }
                else if (args[i] is long longVal)
                {
                    bindResult = SqliteNative.sqlite3_bind_int64(stmt, idx, longVal);
                }
                else
                {
                    byte[] text = SqliteNative.ToUtf8Z(args[i].ToString());
                    // Длину передаём без завершающего нуля, который добавили в ToUtf8Z.
                    bindResult = SqliteNative.sqlite3_bind_text(
                        stmt, idx, text, text.Length - 1, SqliteNative.SQLITE_TRANSIENT);
                }

                if (bindResult != SqliteNative.SQLITE_OK)
                {
                    SqliteNative.sqlite3_finalize(stmt);
                    throw new Exception("Не удалось подставить параметр в SQL-запрос");
                }
            }

            return stmt;
        }

        public void Dispose()
        {
            if (_handle != IntPtr.Zero)
            {
                SqliteNative.sqlite3_close(_handle);
                _handle = IntPtr.Zero;
            }
        }
    }
}
