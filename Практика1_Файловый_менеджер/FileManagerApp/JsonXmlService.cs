using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Xml;
using System.Xml.Serialization;

namespace FileManagerApp
{
    // Пункт 3 задания - экспорт и импорт списка файлов в JSON/XML.
    // Внешний файл считается недоверенным: ограничиваем его размер и количество
    // записей, проверяем поля и используем безопасные настройки XML-парсера.
    internal class JsonXmlService
    {
        private const long MaxImportBytes = 5L * 1024 * 1024; // 5 МБ
        private const int MaxRecords = 10_000;

        private readonly Db _db;
        private readonly UserAccount _user;

        public JsonXmlService(Db db, UserAccount user)
        {
            _db = db;
            _user = user;
        }

        public void ExportFilesToJson(string jsonPath)
        {
            List<FileCard> cards = LoadFileCardsFromDb();
            var options = new JsonSerializerOptions
            {
                WriteIndented = true,
                MaxDepth = 16
            };

            string fullPath = PrepareOutputPath(jsonPath);
            string json = JsonSerializer.Serialize(cards, options);
            File.WriteAllText(fullPath, json);

            LogOperation("export_json", $"Экспортировано {cards.Count} записей в {fullPath}");
            Console.WriteLine($"Сохранено {cards.Count} записей в {fullPath}");
        }

        public void ImportFilesFromJson(string jsonPath)
        {
            string fullPath = CheckInputFile(jsonPath);
            string json = ReadFileLimited(fullPath);

            List<FileCard> cards;
            try
            {
                // Десериализуем в конкретный тип, а не в object/dynamic.
                // JSON должен быть массивом объектов FileCard, иначе будет ошибка.
                var options = new JsonSerializerOptions { MaxDepth = 16 };
                cards = JsonSerializer.Deserialize<List<FileCard>>(json, options) ?? new List<FileCard>();
            }
            catch (JsonException e)
            {
                throw new Exception("Файл не похож на корректный JSON: " + e.Message);
            }

            ImportCards(cards, "json", fullPath);
        }

        public void ExportFilesToXml(string xmlPath)
        {
            List<FileCard> cards = LoadFileCardsFromDb();
            string fullPath = PrepareOutputPath(xmlPath);
            var serializer = new XmlSerializer(typeof(List<FileCard>));

            using (var writer = new StreamWriter(fullPath))
            {
                serializer.Serialize(writer, cards);
            }

            LogOperation("export_xml", $"Экспортировано {cards.Count} записей в {fullPath}");
            Console.WriteLine($"Сохранено {cards.Count} записей в {fullPath}");
        }

        public void ImportFilesFromXml(string xmlPath)
        {
            string fullPath = CheckInputFile(xmlPath);
            var serializer = new XmlSerializer(typeof(List<FileCard>));
            List<FileCard> cards;

            // DTD и внешние сущности в XML нам не нужны. Если их не запретить,
            // можно получить XXE - чтение локальных файлов или обращение к
            // внутренним адресам от имени программы.
            var settings = new XmlReaderSettings
            {
                DtdProcessing = DtdProcessing.Prohibit,
                XmlResolver = null,
                MaxCharactersInDocument = MaxImportBytes
            };

            try
            {
                using (var stream = File.OpenRead(fullPath))
                using (var reader = XmlReader.Create(stream, settings))
                {
                    cards = (List<FileCard>)serializer.Deserialize(reader);
                }
            }
            catch (InvalidOperationException e)
            {
                throw new Exception("Файл не похож на корректный XML: " + e.Message);
            }

            ImportCards(cards ?? new List<FileCard>(), "xml", fullPath);
        }

        // Общая часть импорта: проверяем карточки и заносим их в таблицу Files.
        // Файлы на диске при этом не создаются - импортируются только записи.
        private void ImportCards(List<FileCard> cards, string format, string sourcePath)
        {
            if (cards.Count > MaxRecords)
                throw new Exception($"Слишком много записей: {cards.Count}, максимум {MaxRecords}");

            int added = 0;
            int updated = 0;
            int skipped = 0;

            foreach (FileCard card in cards)
            {
                if (!ValidateCard(card, out string location))
                {
                    skipped++;
                    continue;
                }

                var rows = _db.Query(
                    "SELECT id, owner_id FROM Files WHERE location = ? ORDER BY id DESC LIMIT 1",
                    location);

                if (rows.Count == 0)
                {
                    _db.ExecuteInsert(
                        "INSERT INTO Files (filename, size, location, owner_id) VALUES (?, ?, ?, ?)",
                        card.FileName.Trim(), card.SizeBytes, location, _user.Id);
                    added++;
                }
                else
                {
                    object owner = rows[0]["owner_id"];
                    if (owner != null && (long)owner != _user.Id)
                    {
                        // Чужую запись не трогаем. Молча пропускаем, чтобы один
                        // неверный файл не ломал весь импорт.
                        skipped++;
                        continue;
                    }

                    _db.ExecuteNonQuery(
                        "UPDATE Files SET filename = ?, size = ? WHERE id = ?",
                        card.FileName.Trim(), card.SizeBytes, (long)rows[0]["id"]);
                    updated++;
                }
            }

            LogOperation($"import_{format}",
                $"Импорт из {sourcePath}: добавлено {added}, обновлено {updated}, пропущено {skipped}");

            Console.WriteLine($"Импорт завершён: добавлено {added}, обновлено {updated}, пропущено {skipped}");
        }

        private static bool ValidateCard(FileCard card, out string fullLocation)
        {
            fullLocation = null;

            if (card == null || string.IsNullOrWhiteSpace(card.FileName))
                return false;

            if (card.FileName.Length > 255 || card.SizeBytes < 0)
                return false;

            if (string.IsNullOrWhiteSpace(card.Location) || card.Location.Length > 1024)
                return false;

            try
            {
                fullLocation = Path.GetFullPath(card.Location);
            }
            catch
            {
                // Некорректный путь (например, с недопустимыми символами) -
                // такую запись лучше пропустить, чем ронять весь импорт.
                return false;
            }

            return true;
        }

        private List<FileCard> LoadFileCardsFromDb()
        {
            var rows = _db.Query(
                "SELECT filename, size, location, created_at FROM Files WHERE owner_id = ? ORDER BY id",
                _user.Id);

            var cards = new List<FileCard>();
            foreach (var r in rows)
            {
                cards.Add(new FileCard
                {
                    FileName = (string)r["filename"],
                    SizeBytes = r["size"] == null ? 0 : (long)r["size"],
                    Location = (string)r["location"],
                    CreatedAt = (string)r["created_at"]
                });
            }
            return cards;
        }

        private static string CheckInputPath(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
                throw new Exception("Путь к файлу не должен быть пустым");

            return Path.GetFullPath(path);
        }

        private static string CheckInputFile(string path)
        {
            string fullPath = CheckInputPath(path);
            if (!File.Exists(fullPath))
                throw new Exception("Файл не найден: " + fullPath);

            long length = new FileInfo(fullPath).Length;
            if (length > MaxImportBytes)
                throw new Exception($"Файл слишком большой: {length} байт, максимум {MaxImportBytes}");

            return fullPath;
        }

        private static string ReadFileLimited(string fullPath)
        {
            long length = new FileInfo(fullPath).Length;
            if (length > MaxImportBytes)
                throw new Exception($"Файл слишком большой: {length} байт, максимум {MaxImportBytes}");

            return File.ReadAllText(fullPath);
        }

        private static string PrepareOutputPath(string path)
        {
            string fullPath = CheckInputPath(path);
            string dir = Path.GetDirectoryName(fullPath);

            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                Directory.CreateDirectory(dir);

            return fullPath;
        }

        private void LogOperation(string type, string details)
        {
            _db.ExecuteNonQuery(
                "INSERT INTO Operations (operation_type, user_id, details) VALUES (?, ?, ?)",
                type, _user.Id, details);
        }
    }
}
