using System;
using System.IO;
using System.Text;

namespace FileManagerApp
{
    // Пункт 2 задания - работа с файлами: создать, прочитать, изменить, удалить.
    // Каждое действие пишется в Operations, чтобы потом было видно, кто и что делал.
    //
    // Отдельно добавлен контроль доступа: если файл уже зарегистрирован в БД
    // и принадлежит другому пользователю, читать/менять/удалять его нельзя.
    // Файлы, которых в БД ещё нет (например, только что положенные в папку
    // вручную), считаются общими - иначе файловый менеджер не смог бы открыть
    // ничего, кроме созданного им самим.
    internal class FileOpsService
    {
        private const long MaxTextFileBytes = 10L * 1024 * 1024; // 10 МБ

        private readonly Db _db;
        private readonly UserAccount _user;

        public FileOpsService(Db db, UserAccount user)
        {
            _db = db;
            _user = user;
        }

        public void CreateTextFile(string path, string content)
        {
            string fullPath = PreparePath(path);
            long? existingId = CheckAccess(fullPath, "создавать/перезаписывать");

            WriteTextExclusive(fullPath, content ?? string.Empty);

            var fi = new FileInfo(fullPath);
            long fileId;

            if (existingId.HasValue)
            {
                // Файл уже был в БД (например, его перезаписали через пункт "изменить").
                // Обновляем размер, чтобы данные в таблице Files не расходились с диском.
                _db.ExecuteNonQuery("UPDATE Files SET size = ? WHERE id = ?", fi.Length, existingId.Value);
                fileId = existingId.Value;
            }
            else
            {
                fileId = _db.ExecuteInsert(
                    "INSERT INTO Files (filename, size, location, owner_id) VALUES (?, ?, ?, ?)",
                    fi.Name, fi.Length, fi.FullName, _user.Id);
            }

            LogOperation("create", fileId, $"Создан файл {fi.FullName}, {fi.Length} байт");
            Console.WriteLine($"Файл создан, запись в БД id = {fileId}");
        }

        public void ReadTextFile(string path)
        {
            string fullPath = PreparePath(path);

            if (!File.Exists(fullPath))
            {
                Console.WriteLine("Файл не найден: " + fullPath);
                return;
            }

            CheckAccess(fullPath, "читать");

            var fi = new FileInfo(fullPath);
            if (fi.Length > MaxTextFileBytes)
            {
                Console.WriteLine($"Файл больше {MaxTextFileBytes / 1024 / 1024} МБ, читать целиком не буду");
                return;
            }

            Console.WriteLine("--- содержимое файла ---");
            Console.WriteLine(File.ReadAllText(fullPath));
            Console.WriteLine("------------------------");

            LogOperation("read", FindFileId(fullPath), "Прочитан файл " + fullPath);
        }

        // Изменение файла - то, чего не хватало для пункта 5 задания
        // ("создание, удаление, изменение файлов" должны попадать в журнал).
        public void ModifyTextFile(string path, string newContent)
        {
            string fullPath = PreparePath(path);
            long? existingId = CheckAccess(fullPath, "изменять");
            bool existed = File.Exists(fullPath);

            WriteTextExclusive(fullPath, newContent ?? string.Empty);

            var fi = new FileInfo(fullPath);
            long fileId;

            if (existingId.HasValue)
            {
                _db.ExecuteNonQuery("UPDATE Files SET size = ? WHERE id = ?", fi.Length, existingId.Value);
                fileId = existingId.Value;
            }
            else
            {
                fileId = _db.ExecuteInsert(
                    "INSERT INTO Files (filename, size, location, owner_id) VALUES (?, ?, ?, ?)",
                    fi.Name, fi.Length, fi.FullName, _user.Id);
            }

            string action = existed ? "изменён" : "создан";
            LogOperation("modify", fileId, $"Файл {action}: {fi.FullName}, {fi.Length} байт");
            Console.WriteLine($"Файл {action}, запись в БД id = {fileId}");
        }

        public void DeleteFile(string path)
        {
            string fullPath = PreparePath(path);
            long? fileId = CheckAccess(fullPath, "удалять");

            if (!File.Exists(fullPath))
            {
                Console.WriteLine("Файл не найден: " + fullPath);
                return;
            }

            File.Delete(fullPath);

            // Строку из Files убираем, но журнал операций не трогаем - он нужен
            // для аудита. Чтобы внешний ключ не указывал на удалённую запись,
            // заранее обнуляем file_id у старых операций.
            if (fileId.HasValue)
            {
                _db.ExecuteNonQuery("UPDATE Operations SET file_id = NULL WHERE file_id = ?", fileId.Value);
                _db.ExecuteNonQuery("DELETE FROM Files WHERE id = ?", fileId.Value);
            }

            LogOperation("delete", null, "Удалён файл " + fullPath);
            Console.WriteLine("Файл удалён");
        }

        private string PreparePath(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
                throw new Exception("Путь к файлу не должен быть пустым");

            return Path.GetFullPath(path);
        }

        // Возвращает id записи в Files, если файл уже известен программе.
        // Заодно проверяет, что текущий пользователь имеет право с ним работать.
        private long? CheckAccess(string fullPath, string action)
        {
            var rows = _db.Query(
                "SELECT id, owner_id FROM Files WHERE location = ? ORDER BY id DESC LIMIT 1",
                fullPath);

            if (rows.Count == 0)
                return null;

            long id = (long)rows[0]["id"];
            object owner = rows[0]["owner_id"];

            if (owner != null && (long)owner != _user.Id)
                throw new Exception($"Нет прав {action} этот файл: он принадлежит другому пользователю");

            return id;
        }

        private long? FindFileId(string fullPath)
        {
            var rows = _db.Query(
                "SELECT id FROM Files WHERE location = ? ORDER BY id DESC LIMIT 1", fullPath);
            return rows.Count > 0 ? (long)rows[0]["id"] : (long?)null;
        }

        // FileShare.None не даёт двум экземплярам программы одновременно писать
        // один и тот же файл. Без этого при параллельном запуске получилась бы
        // классическая гонка: оба прочитали старое содержимое и оба записали своё.
        private static void WriteTextExclusive(string fullPath, string content)
        {
            string dir = Path.GetDirectoryName(fullPath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                Directory.CreateDirectory(dir);

            using (var stream = new FileStream(fullPath, FileMode.Create, FileAccess.Write, FileShare.None))
            using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
            {
                writer.Write(content);
            }
        }

        private void LogOperation(string type, long? fileId, string details)
        {
            _db.ExecuteNonQuery(
                "INSERT INTO Operations (operation_type, file_id, user_id, details) VALUES (?, ?, ?, ?)",
                type, fileId, _user.Id, details);
        }
    }
}
