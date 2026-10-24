namespace FileManagerApp
{
    // Текущий авторизованный пользователь - просто данные,
    // которые передаём между сервисами, чтобы знать кто сейчас работает
    internal class UserAccount
    {
        public long Id { get; set; }
        public string Username { get; set; }
    }

    // "Карточка" файла для экспорта/импорта в JSON и XML.
    // Публичный класс и публичные свойства с get/set обязательны -
    // и JsonSerializer, и XmlSerializer сериализуют только публичные
    // свойства с обоими аксессорами
    public class FileCard
    {
        public string FileName { get; set; }
        public long SizeBytes { get; set; }
        public string Location { get; set; }
        public string CreatedAt { get; set; }
    }
}
