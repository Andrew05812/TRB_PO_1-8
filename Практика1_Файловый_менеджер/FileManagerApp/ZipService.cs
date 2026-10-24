using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;

namespace FileManagerApp
{
    // Пункт 4 задания - ZIP-архивы. При распаковке архив считается
    // потенциально враждебным: проверяем количество файлов, размер каждого,
    // общий размер и путь (защита от zip-бомбы и path traversal).
    internal class ZipService
    {
        private const int MaxEntries = 5_000;
        private const long MaxEntryBytes = 200L * 1024 * 1024;   // 200 МБ на файл
        private const long MaxTotalBytes = 500L * 1024 * 1024;   // 500 МБ всего
        private const double MaxCompressionRatio = 1_000.0;

        private readonly Db _db;
        private readonly UserAccount _user;

        public ZipService(Db db, UserAccount user)
        {
            _db = db;
            _user = user;
        }

        public void CreateArchive(string sourceDir, string zipPath)
        {
            if (string.IsNullOrWhiteSpace(sourceDir) || string.IsNullOrWhiteSpace(zipPath))
                throw new Exception("Папка и путь к архиву должны быть указаны");

            string fullSource = Path.GetFullPath(sourceDir);
            string fullZip = Path.GetFullPath(zipPath);

            if (!Directory.Exists(fullSource))
            {
                Console.WriteLine("Папка не найдена: " + fullSource);
                return;
            }

            // Если положить архив внутрь архивируемой папки, при повторном
            // запуске он начнёт включать сам себя. Проще запретить сразу.
            if (IsInside(fullZip, fullSource))
                throw new Exception("Архив нельзя создавать внутри папки, которую архивируем");

            string dir = Path.GetDirectoryName(fullZip);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                Directory.CreateDirectory(dir);

            if (File.Exists(fullZip))
                File.Delete(fullZip);

            ZipFile.CreateFromDirectory(fullSource, fullZip, CompressionLevel.Optimal, false);

            LogOperation("zip", $"Папка {fullSource} заархивирована в {fullZip}");
            Console.WriteLine("Архив создан: " + fullZip);
        }

        public void ExtractArchive(string zipPath, string targetDir)
        {
            if (string.IsNullOrWhiteSpace(zipPath) || string.IsNullOrWhiteSpace(targetDir))
                throw new Exception("Путь к архиву и папка назначения должны быть указаны");

            string fullZip = Path.GetFullPath(zipPath);
            string fullTargetDir = Path.GetFullPath(targetDir);

            if (!File.Exists(fullZip))
            {
                Console.WriteLine("Архив не найден: " + fullZip);
                return;
            }

            Directory.CreateDirectory(fullTargetDir);
            string targetPrefix = fullTargetDir.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;

            var createdFiles = new List<string>();

            try
            {
                using (ZipArchive archive = ZipFile.OpenRead(fullZip))
                {
                    if (archive.Entries.Count > MaxEntries)
                        throw new Exception($"В архиве {archive.Entries.Count} записей, максимум {MaxEntries}");

                    long totalBytes = 0;

                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        string relative = entry.FullName.Replace('\\', '/');

                        if (relative.Length == 0)
                            continue;

                        // Абсолютные пути и буквы диска не должны попадать даже
                        // в проверку: Path.Combine может просто отбросить targetDir.
                        if (relative.StartsWith("/") || relative.Contains(":"))
                            throw new Exception($"Недопустимый путь в архиве: {entry.FullName}");

                        string destPath = Path.GetFullPath(Path.Combine(targetPrefix, relative));
                        if (!IsInsideOrEqual(destPath, fullTargetDir))
                            throw new Exception($"Запись \"{entry.FullName}\" выходит за пределы папки назначения");

                        bool isDirectory = entry.FullName.EndsWith("/") || string.IsNullOrEmpty(entry.Name);
                        if (isDirectory)
                        {
                            Directory.CreateDirectory(destPath);
                            continue;
                        }

                        if (entry.Length > MaxEntryBytes)
                            throw new Exception($"Файл \"{entry.FullName}\" слишком большой: {entry.Length} байт");

                        // Сильно сжатый файл - типичный признак zip-бомбы.
                        // Проверяем только большие файлы, чтобы не ругаться на
                        // обычные маленькие тексты с большим коэффициентом сжатия.
                        if (entry.Length > 1024 * 1024 && entry.CompressedLength > 0)
                        {
                            double ratio = (double)entry.Length / entry.CompressedLength;
                            if (ratio > MaxCompressionRatio)
                                throw new Exception($"Подозрительная степень сжатия у \"{entry.FullName}\": {ratio:F0}:1");
                        }

                        string parent = Path.GetDirectoryName(destPath);
                        if (!string.IsNullOrEmpty(parent))
                            Directory.CreateDirectory(parent);

                        if (Directory.Exists(destPath))
                            throw new Exception($"Нельзя распаковать файл поверх папки: {destPath}");

                        // Распаковываем вручную, а не ZipFile.ExtractToDirectory:
                        // так мы считаем реально записанные байты и можем
                        // остановиться, даже если в заголовке архива размер соврал.
                        createdFiles.Add(destPath);
                        long entryBytes = 0;
                        byte[] buffer = new byte[64 * 1024];

                        using (Stream input = entry.Open())
                        using (var output = new FileStream(destPath, FileMode.Create, FileAccess.Write, FileShare.None))
                        {
                            int read;
                            while ((read = input.Read(buffer, 0, buffer.Length)) > 0)
                            {
                                entryBytes += read;
                                totalBytes += read;

                                if (entryBytes > MaxEntryBytes)
                                    throw new Exception($"Файл \"{entry.FullName}\" распаковывается больше {MaxEntryBytes} байт");
                                if (totalBytes > MaxTotalBytes)
                                    throw new Exception("Архив слишком большой в распакованном виде - распаковка остановлена");

                                output.Write(buffer, 0, read);
                            }
                        }
                    }
                }

                LogOperation("unzip", $"Архив {fullZip} распакован в {fullTargetDir}");
                Console.WriteLine("Архив распакован в " + fullTargetDir);
            }
            catch
            {
                // Не оставляем в папке половину распакованного архива.
                foreach (string file in createdFiles)
                {
                    try { File.Delete(file); } catch { /* уже удалён или занят */ }
                }
                throw;
            }
        }

        private static bool IsInside(string path, string directory)
        {
            string prefix = directory.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            return path.StartsWith(prefix, PathComparison());
        }

        private static bool IsInsideOrEqual(string path, string directory)
        {
            return path.Equals(directory, PathComparison()) || IsInside(path, directory);
        }

        private static StringComparison PathComparison()
        {
            // На Windows регистр в путях не важен, на Linux - важен.
            return RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
                ? StringComparison.OrdinalIgnoreCase
                : StringComparison.Ordinal;
        }

        private void LogOperation(string type, string details)
        {
            _db.ExecuteNonQuery(
                "INSERT INTO Operations (operation_type, user_id, details) VALUES (?, ?, ?)",
                type, _user.Id, details);
        }
    }
}
