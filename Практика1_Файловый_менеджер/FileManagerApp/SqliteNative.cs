using System;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;

namespace FileManagerApp
{
    // Тонкая обёртка над нативной SQLite.
    //
    // Изначально здесь был жёстко прописан "libsqlite3.so.0" - это имя
    // библиотеки в Linux (Astra Linux в аудитории). На Windows такой файл
    // не найдётся, поэтому теперь имя выбирается во время запуска:
    //   Windows -> winsqlite3.dll (SQLite входит в состав системы)
    //   Linux   -> libsqlite3.so.0 / libsqlite3.so
    //   macOS   -> libsqlite3.dylib
    //
    // P/Invoke-объявления ниже ссылаются на условное имя "sqlite3", а какой
    // реальный файл загрузить, решает NativeLibrary в статическом конструкторе.
    internal static class SqliteNative
    {
        private const string Lib = "sqlite3";

        static SqliteNative()
        {
            NativeLibrary.SetDllImportResolver(typeof(SqliteNative).Assembly, ResolveSqlite);
        }

        private static IntPtr ResolveSqlite(string libraryName, Assembly assembly, DllImportSearchPath? searchPath)
        {
            if (libraryName != Lib)
                return IntPtr.Zero;

            string[] candidates;

            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            {
                // winsqlite3.dll есть в Windows 10/11 из коробки. Остальные
                // варианты оставлены на случай, если рядом с программой
                // положили свою копию SQLite.
                candidates = new[] { "winsqlite3.dll", "sqlite3.dll", "e_sqlite3.dll" };
            }
            else if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
            {
                candidates = new[] { "libsqlite3.dylib", "/usr/lib/libsqlite3.dylib" };
            }
            else
            {
                candidates = new[] { "libsqlite3.so.0", "libsqlite3.so" };
            }

            foreach (string name in candidates)
            {
                if (NativeLibrary.TryLoad(name, assembly, searchPath, out IntPtr handle))
                    return handle;
            }

            throw new DllNotFoundException(
                "Не удалось загрузить SQLite. Проверьте, что в системе есть " +
                "winsqlite3.dll (Windows) или пакет libsqlite3 (Linux).");
        }

        // Вызывать нужно именно cdecl: у SQLite обычные C-функции, а не WinAPI.
        // На x64 соглашение одно, но на x86 без этого программа падала бы.
        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_open(
            [MarshalAs(UnmanagedType.LPUTF8Str)] string filename,
            out IntPtr db);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_close(IntPtr db);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_prepare_v2(
            IntPtr db, byte[] sql, int nBytes, out IntPtr stmt, IntPtr tail);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_step(IntPtr stmt);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_finalize(IntPtr stmt);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_bind_text(
            IntPtr stmt, int index, byte[] value, int n, IntPtr destructor);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_bind_int64(IntPtr stmt, int index, long value);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_bind_null(IntPtr stmt, int index);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr sqlite3_column_text(IntPtr stmt, int col);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern long sqlite3_column_int64(IntPtr stmt, int col);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_column_type(IntPtr stmt, int col);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_column_count(IntPtr stmt);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr sqlite3_column_name(IntPtr stmt, int col);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr sqlite3_errmsg(IntPtr db);

        [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
        public static extern long sqlite3_last_insert_rowid(IntPtr db);

        // Коды, которые реально встречаются в проекте.
        public const int SQLITE_OK = 0;
        public const int SQLITE_ROW = 100;
        public const int SQLITE_DONE = 101;
        public const int SQLITE_INTEGER = 1;
        public const int SQLITE_NULL = 5;

        // SQLITE_TRANSIENT = (sqlite3_destructor_type)-1: SQLite сам скопирует
        // строку себе, а наш временный массив можно спокойно освобождать.
        public static readonly IntPtr SQLITE_TRANSIENT = new IntPtr(-1);

        public static string PtrToUtf8String(IntPtr ptr)
        {
            if (ptr == IntPtr.Zero)
                return null;

            // SQLite возвращает C-строку в UTF-8, поэтому сначала считаем
            // длину до нулевого байта, затем копируем и декодируем.
            int len = 0;
            while (Marshal.ReadByte(ptr, len) != 0)
                len++;

            byte[] buffer = new byte[len];
            Marshal.Copy(ptr, buffer, 0, len);
            return Encoding.UTF8.GetString(buffer);
        }

        public static byte[] ToUtf8Z(string s)
        {
            byte[] bytes = Encoding.UTF8.GetBytes(s ?? string.Empty);
            byte[] withZero = new byte[bytes.Length + 1];
            Array.Copy(bytes, withZero, bytes.Length);
            return withZero;
        }
    }
}
