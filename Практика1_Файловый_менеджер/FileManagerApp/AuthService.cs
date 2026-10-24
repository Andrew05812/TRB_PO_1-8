using System;
using System.Security.Cryptography;

namespace FileManagerApp
{
    // Регистрация и вход. Пароли нигде не хранятся в открытом виде -
    // только PBKDF2-хэш + случайная соль под каждого пользователя
    // (см. схему таблицы Users в методичке: "пароль зафиксирован хешированным значением").
    internal class AuthService
    {
        private readonly Db _db;

        private const int SaltSizeBytes = 16;
        private const int HashSizeBytes = 32;
        // 100 000 итераций - намеренно "дорого" по времени, чтобы массовый
        // перебор хэшей из украденной БД был ощутимо медленнее, чем с голым SHA-256
        private const int Iterations = 100_000;

        private const int MinPasswordLength = 8;
        private const int MaxPasswordLength = 128;

        // Соль для "пустой" проверки пароля, когда такого логина нет.
        // Нужна, чтобы вход с несуществующим логином занимал примерно столько
        // же времени, сколько с существующим: иначе по секундомеру можно
        // понять, какие логины в системе есть.
        private static readonly byte[] DummySalt = new byte[]
        {
            0x51, 0x7A, 0x2C, 0x9F, 0x13, 0x88, 0xAB, 0x04,
            0x6D, 0xE1, 0x37, 0x42, 0xBC, 0x90, 0x5A, 0xF8
        };

        public AuthService(Db db)
        {
            _db = db;
        }

        public UserAccount Register(string username, string password)
        {
            username = (username ?? string.Empty).Trim();

            if (username.Length < 3 || username.Length > 50)
                throw new Exception("Логин должен быть длиной от 3 до 50 символов");
            if (string.IsNullOrWhiteSpace(password))
                throw new Exception("Пароль не должен быть пустым");
            if (password.Length < MinPasswordLength)
                throw new Exception($"Пароль должен быть не короче {MinPasswordLength} символов");
            if (password.Length > MaxPasswordLength)
                throw new Exception($"Пароль должен быть не длиннее {MaxPasswordLength} символов");

            var existing = _db.Query("SELECT id FROM Users WHERE username = ?", username);
            if (existing.Count > 0)
                throw new Exception("Пользователь с таким логином уже есть");

            byte[] salt = RandomNumberGenerator.GetBytes(SaltSizeBytes);
            string saltHex = Convert.ToHexString(salt);
            string hashHex = HashPassword(password, salt);

            long id = _db.ExecuteInsert(
                "INSERT INTO Users (username, password_hash, salt) VALUES (?, ?, ?)",
                username, hashHex, saltHex);

            return new UserAccount { Id = id, Username = username };
        }

        public UserAccount Login(string username, string password)
        {
            username = (username ?? string.Empty).Trim();
            password = password ?? string.Empty;

            // Слишком длинный пароль отсекаем до вычисления хэша: иначе одна
            // такая попытка может надолго занять процессор.
            if (password.Length > MaxPasswordLength)
                throw new Exception("Неверный логин или пароль");

            var rows = _db.Query("SELECT id, password_hash, salt FROM Users WHERE username = ?", username);

            // Специально не говорим отдельно "нет такого логина" и "неверный пароль" -
            // иначе по тексту ошибки можно перебором узнавать, какие логины вообще существуют.
            // Хэш всё равно считаем, чтобы не выдавать отсутствие логина временем ответа.
            if (rows.Count == 0)
            {
                HashPassword(password, DummySalt);
                throw new Exception("Неверный логин или пароль");
            }

            var row = rows[0];
            byte[] salt = Convert.FromHexString((string)row["salt"]);
            string expectedHashHex = (string)row["password_hash"];
            string actualHashHex = HashPassword(password, salt);

            byte[] expected = Convert.FromHexString(expectedHashHex);
            byte[] actual = Convert.FromHexString(actualHashHex);

            // Сравниваем хэши через FixedTimeEquals, а не через ==/SequenceEqual -
            // обычное сравнение строк останавливается на первом несовпавшем байте,
            // и по времени ответа теоретически можно подбирать хэш побайтово (timing attack)
            bool ok = CryptographicOperations.FixedTimeEquals(actual, expected);
            if (!ok)
                throw new Exception("Неверный логин или пароль");

            return new UserAccount { Id = (long)row["id"], Username = username };
        }

        private static string HashPassword(string password, byte[] salt)
        {
            using var pbkdf2 = new Rfc2898DeriveBytes(password, salt, Iterations, HashAlgorithmName.SHA256);
            byte[] hash = pbkdf2.GetBytes(HashSizeBytes);
            return Convert.ToHexString(hash);
        }
    }
}
