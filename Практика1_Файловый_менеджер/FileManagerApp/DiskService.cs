using System;
using System.IO;

namespace FileManagerApp
{
    // Пункт 1 задания - список дисков и их свойства.
    // Всё берём из System.IO.DriveInfo, прямо как в теоретической части методички
    internal static class DiskService
    {
        public static void PrintDrives()
        {
            DriveInfo[] drives = DriveInfo.GetDrives();

            foreach (DriveInfo d in drives)
            {
                Console.WriteLine($"Диск/точка монтирования: {d.Name}");
                Console.WriteLine($"  Тип: {d.DriveType}");

                // IsReady важно проверять первым - у несмонтированных дисков
                // (например, пустой CD-привод) чтение остальных свойств упадёт с исключением
                if (d.IsReady)
                {
                    Console.WriteLine($"  Файловая система: {d.DriveFormat}");
                    Console.WriteLine($"  Метка тома: {d.VolumeLabel}");
                    Console.WriteLine($"  Всего места: {d.TotalSize / 1024 / 1024} МБ");
                    Console.WriteLine($"  Свободно: {d.AvailableFreeSpace / 1024 / 1024} МБ");
                }
                else
                {
                    Console.WriteLine("  (диск не готов / не примонтирован)");
                }
                Console.WriteLine();
            }
        }
    }
}
