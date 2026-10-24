using System;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.Json;

namespace FileManagerApp
{
    // Консольный файловый менеджер - Практика 1.
    // Колесников А.Ю., БСБО-03-23, студ. билет 23Б0099
    internal class Program
    {
        private const string DbPath = "filemanager.db";

        static int Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;

            // --selfcheck нужен для CI (см. Практику 2) и для быстрой проверки
            // своими руками без ввода с клавиатуры: прогоняет по очереди все модули
            // и завершает процесс с ненулевым кодом, если что-то упало
            if (args.Length > 0 && args[0] == "--selfcheck")
                return RunSelfCheck() ? 0 : 1;

            Console.WriteLine("=== Файловый менеджер (Практика 1, БСБО-03-23, Колесников А.Ю.) ===\n");

            using (var db = new Db(DbPath))
            {
                var auth = new AuthService(db);
                UserAccount user = LoginOrRegister(auth);

                Console.WriteLine($"\nДобро пожаловать, {user.Username}!\n");

                var fileOps = new FileOpsService(db, user);
                var jsonXml = new JsonXmlService(db, user);
                var zip = new ZipService(db, user);

                RunMainMenu(db, user, fileOps, jsonXml, zip);
            }

            return 0;
        }

        private static UserAccount LoginOrRegister(AuthService auth)
        {
            while (true)
            {
                Console.WriteLine("1 - Войти");
                Console.WriteLine("2 - Зарегистрироваться");
                Console.Write("Выбор: ");
                string choice = Console.ReadLine();

                Console.Write("Логин: ");
                string username = Console.ReadLine();
                Console.Write("Пароль: ");
                string password = ReadPasswordMasked();

                try
                {
                    return choice == "2" ? auth.Register(username, password) : auth.Login(username, password);
                }
                catch (Exception e)
                {
                    Console.WriteLine("Ошибка: " + e.Message + "\n");
                }
            }
        }

        // Чтобы пароль не отображался на экране открытым текстом, читаем ввод
        // посимвольно через Console.ReadKey и рисуем звёздочки вместо символов
        private static string ReadPasswordMasked()
        {
            var pass = new StringBuilder();
            ConsoleKeyInfo key;

            while ((key = Console.ReadKey(true)).Key != ConsoleKey.Enter)
            {
                if (key.Key == ConsoleKey.Backspace && pass.Length > 0)
                {
                    pass.Length--;
                    Console.Write("\b \b");
                }
                else if (!char.IsControl(key.KeyChar))
                {
                    pass.Append(key.KeyChar);
                    Console.Write("*");
                }
            }
            Console.WriteLine();
            return pass.ToString();
        }

        private static void RunMainMenu(Db db, UserAccount user, FileOpsService fileOps, JsonXmlService jsonXml, ZipService zip)
        {
            while (true)
            {
                Console.WriteLine("\n--- Главное меню ---");
                Console.WriteLine(" 1 - Список дисков");
                Console.WriteLine(" 2 - Создать текстовый файл");
                Console.WriteLine(" 3 - Прочитать файл");
                Console.WriteLine(" 4 - Изменить файл");
                Console.WriteLine(" 5 - Удалить файл");
                Console.WriteLine(" 6 - Экспорт моих файлов (из БД) в JSON");
                Console.WriteLine(" 7 - Импорт файлов из JSON");
                Console.WriteLine(" 8 - Экспорт моих файлов (из БД) в XML");
                Console.WriteLine(" 9 - Импорт файлов из XML");
                Console.WriteLine("10 - Заархивировать папку в ZIP");
                Console.WriteLine("11 - Распаковать ZIP");
                Console.WriteLine("12 - Показать журнал действий (из БД)");
                Console.WriteLine(" 0 - Выход");
                Console.Write("Выбор: ");

                string choice = Console.ReadLine();
                try
                {
                    switch (choice)
                    {
                        case "1":
                            DiskService.PrintDrives();
                            break;
                        case "2":
                            Console.Write("Путь к файлу: ");
                            string createPath = Console.ReadLine();
                            Console.Write("Текст: ");
                            string content = Console.ReadLine();
                            fileOps.CreateTextFile(createPath, content);
                            break;
                        case "3":
                            Console.Write("Путь к файлу: ");
                            fileOps.ReadTextFile(Console.ReadLine());
                            break;
                        case "4":
                            Console.Write("Путь к файлу: ");
                            string modifyPath = Console.ReadLine();
                            Console.Write("Новый текст: ");
                            string newContent = Console.ReadLine();
                            fileOps.ModifyTextFile(modifyPath, newContent);
                            break;
                        case "5":
                            Console.Write("Путь к файлу: ");
                            fileOps.DeleteFile(Console.ReadLine());
                            break;
                        case "6":
                            Console.Write("Путь к json-файлу: ");
                            jsonXml.ExportFilesToJson(Console.ReadLine());
                            break;
                        case "7":
                            Console.Write("Путь к json-файлу: ");
                            jsonXml.ImportFilesFromJson(Console.ReadLine());
                            break;
                        case "8":
                            Console.Write("Путь к xml-файлу: ");
                            jsonXml.ExportFilesToXml(Console.ReadLine());
                            break;
                        case "9":
                            Console.Write("Путь к xml-файлу: ");
                            jsonXml.ImportFilesFromXml(Console.ReadLine());
                            break;
                        case "10":
                            Console.Write("Папка для архивации: ");
                            string srcDir = Console.ReadLine();
                            Console.Write("Путь к zip-файлу: ");
                            string zipPath = Console.ReadLine();
                            zip.CreateArchive(srcDir, zipPath);
                            break;
                        case "11":
                            Console.Write("Путь к zip-файлу: ");
                            string zipToExtract = Console.ReadLine();
                            Console.Write("Папка для распаковки: ");
                            string targetDir = Console.ReadLine();
                            zip.ExtractArchive(zipToExtract, targetDir);
                            break;
                        case "12":
                            PrintOperationsLog(db, user);
                            break;
                        case "0":
                            return;
                        default:
                            Console.WriteLine("Нет такого пункта меню");
                            break;
                    }
                }
                catch (Exception e)
                {
                    Console.WriteLine("Ошибка: " + e.Message);
                }
            }
        }

        private static void PrintOperationsLog(Db db, UserAccount user)
        {
            var rows = db.Query(
                "SELECT op_time, operation_type, details FROM Operations WHERE user_id = ? ORDER BY id DESC LIMIT 50",
                user.Id);

            Console.WriteLine("\n--- Последние действия (не более 50) ---");
            foreach (var r in rows)
                Console.WriteLine($"{r["op_time"]} | {r["operation_type"],-12} | {r["details"]}");
        }

        // Автоматическая проверка без участия человека - прогоняем по очереди
        // все модули программы на временных файлах и смотрим, что ничего не падает.
        // Используется в CI-конвейере из Практики 2 на стадии test.
        private static bool RunSelfCheck()
        {
            string workDir = Path.Combine(Path.GetTempPath(), "fm_selfcheck_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(workDir);
            string dbPath = Path.Combine(workDir, "selfcheck.db");

            try
            {
                using (var db = new Db(dbPath))
                {
                    var auth = new AuthService(db);
                    UserAccount user = auth.Register("selfcheck_user", "SelfCheckPass123!");

                    // логин должен сработать с тем же паролем
                    UserAccount loggedIn = auth.Login("selfcheck_user", "SelfCheckPass123!");
                    Assert(loggedIn.Id == user.Id, "Login должен вернуть того же пользователя, что Register");

                    // и не должен срабатывать с неверным паролем
                    bool wrongPasswordRejected = false;
                    try { auth.Login("selfcheck_user", "неверный_пароль"); }
                    catch { wrongPasswordRejected = true; }
                    Assert(wrongPasswordRejected, "Login с неверным паролем должен бросать исключение");

                    // слишком короткий пароль регистрировать нельзя
                    bool shortPasswordRejected = false;
                    try { auth.Register("short_user", "123"); }
                    catch { shortPasswordRejected = true; }
                    Assert(shortPasswordRejected, "Короткий пароль должен отклоняться");

                    var fileOps = new FileOpsService(db, user);
                    string testFile = Path.Combine(workDir, "note.txt");
                    fileOps.CreateTextFile(testFile, "привет из selfcheck");
                    Assert(File.Exists(testFile), "Файл должен быть создан на диске");

                    fileOps.ModifyTextFile(testFile, "изменено в selfcheck");
                    Assert(File.ReadAllText(testFile) == "изменено в selfcheck", "Файл должен измениться");
                    var sizeRows = db.Query("SELECT size FROM Files WHERE location = ?", Path.GetFullPath(testFile));
                    Assert(sizeRows.Count == 1 && (long)sizeRows[0]["size"] == new FileInfo(testFile).Length,
                        "Размер файла в БД должен обновиться");

                    // второй пользователь не должен читать чужой файл
                    UserAccount user2 = auth.Register("selfcheck_user2", "AnotherPass456!");
                    var fileOps2 = new FileOpsService(db, user2);
                    bool accessDenied = false;
                    try { fileOps2.ReadTextFile(testFile); }
                    catch { accessDenied = true; }
                    Assert(accessDenied, "Чужой файл не должен читаться");

                    var jsonXml = new JsonXmlService(db, user);
                    string jsonPath = Path.Combine(workDir, "files.json");
                    jsonXml.ExportFilesToJson(jsonPath);
                    Assert(File.Exists(jsonPath), "JSON-экспорт должен создать файл");
                    jsonXml.ImportFilesFromJson(jsonPath);

                    // импорт должен не просто распечатать записи, а сохранить их в БД
                    string importJsonPath = Path.Combine(workDir, "import.json");
                    File.WriteAllText(importJsonPath, JsonSerializer.Serialize(new[]
                    {
                        new FileCard
                        {
                            FileName = "imported.txt",
                            SizeBytes = 5,
                            Location = Path.Combine(workDir, "imported.txt"),
                            CreatedAt = "2026-01-01 12:00:00"
                        }
                    }));
                    jsonXml.ImportFilesFromJson(importJsonPath);
                    var imported = db.Query(
                        "SELECT COUNT(*) AS cnt FROM Files WHERE filename = 'imported.txt' AND owner_id = ?",
                        user.Id);
                    Assert((long)imported[0]["cnt"] == 1, "Импортированная запись должна появиться в БД");

                    string xmlPath = Path.Combine(workDir, "files.xml");
                    jsonXml.ExportFilesToXml(xmlPath);
                    Assert(File.Exists(xmlPath), "XML-экспорт должен создать файл");
                    jsonXml.ImportFilesFromXml(xmlPath);

                    var zip = new ZipService(db, user);
                    string zipDirToArchive = Path.Combine(workDir, "to_zip");
                    Directory.CreateDirectory(zipDirToArchive);
                    File.WriteAllText(Path.Combine(zipDirToArchive, "a.txt"), "test");
                    string zipPath = Path.Combine(workDir, "archive.zip");
                    zip.CreateArchive(zipDirToArchive, zipPath);
                    Assert(File.Exists(zipPath), "ZIP-архив должен быть создан");

                    string extractDir = Path.Combine(workDir, "extracted");
                    zip.ExtractArchive(zipPath, extractDir);
                    Assert(File.Exists(Path.Combine(extractDir, "a.txt")), "Файл внутри архива должен быть распакован");

                    // архив с "../evil.txt" не должен распаковаться за пределы папки
                    string badZipPath = Path.Combine(workDir, "bad.zip");
                    using (var badStream = new FileStream(badZipPath, FileMode.Create))
                    using (var badArchive = new ZipArchive(badStream, ZipArchiveMode.Create))
                    {
                        var badEntry = badArchive.CreateEntry("../evil.txt");
                        using (var writer = new StreamWriter(badEntry.Open()))
                            writer.Write("вредоносная запись");
                    }

                    bool traversalRejected = false;
                    try { zip.ExtractArchive(badZipPath, Path.Combine(workDir, "bad_extract")); }
                    catch { traversalRejected = true; }
                    Assert(traversalRejected, "ZIP с выходом за папку назначения должен отклоняться");
                    Assert(!File.Exists(Path.Combine(workDir, "evil.txt")), "Файл не должен появиться вне папки распаковки");

                    fileOps.DeleteFile(testFile);
                    Assert(!File.Exists(testFile), "Файл должен быть удалён");
                    var afterDelete = db.Query("SELECT COUNT(*) AS cnt FROM Files WHERE location = ?", testFile);
                    Assert((long)afterDelete[0]["cnt"] == 0, "Запись удалённого файла должна исчезнуть из БД");

                    var log = db.Query("SELECT COUNT(*) as cnt FROM Operations WHERE user_id = ?", user.Id);
                    long opsCount = (long)log[0]["cnt"];
                    Assert(opsCount > 0, "В журнале операций должны появиться записи");
                    var modifyLog = db.Query(
                        "SELECT COUNT(*) AS cnt FROM Operations WHERE user_id = ? AND operation_type = 'modify'",
                        user.Id);
                    Assert((long)modifyLog[0]["cnt"] > 0, "Изменение файла должно попадать в журнал");
                }

                Console.WriteLine("SELFCHECK: все проверки пройдены успешно (" + DateTime.Now + ")");
                return true;
            }
            catch (Exception e)
            {
                Console.WriteLine("SELFCHECK FAILED: " + e.Message);
                return false;
            }
            finally
            {
                try { Directory.Delete(workDir, true); } catch { /* не критично, если не удалилось */ }
            }
        }

        private static void Assert(bool condition, string message)
        {
            if (!condition)
                throw new Exception("Проверка не пройдена: " + message);
            Console.WriteLine("  OK: " + message);
        }
    }
}
