using System;
using System.Data.SqlClient;
using System.Diagnostics;
using System.IO;
using System.Runtime.Serialization.Formatters.Binary;
using System.Security.Cryptography;

namespace SastDemo
{
    // Намеренно плохой код. Нужен ровно для одного: показать, что стадия SAST в
    // .gitlab-ci.yml действительно останавливает конвейер, а не молча проходит
    // по чистому проекту. Рабочее приложение из Практики 1 так не делает -
    // напротив, в нём каждый из этих приёмов закрыт другим способом, и это
    // разбираю построчно в таблице ревью.
    //
    // Файл не входит в сборку FileManagerApp: он лежит вне папки проекта, а
    // .csproj подхватывает только .cs-файлы внутри своей папки. В образ он
    // тоже не попадает. Нужен только как мишень для сканера.
    public class UnsafeFileRepository
    {
        // CWE-798: секрет прямо в исходнике. В GitLab такие вещи уходят в
        // Settings -> CI/CD -> Variables с флагом Masked.
        private const string DbPassword = "Sa12!manageR";

        private readonly string _root = @"C:\app\data";

        // CWE-89: SQL собирается конкатенацией из пользовательского ввода.
        // Имя файла вида x'; DROP TABLE Files; -- уходит в запрос как код.
        public string ReadFileBad(string userName, string fileName)
        {
            var conn = new SqlConnection("Server=.;Password=" + DbPassword + ";Database=files");
            var cmd = new SqlCommand(
                "SELECT content FROM Files WHERE owner = '" + userName +
                "' AND name = '" + fileName + "'");
            conn.Open();
            cmd.Connection = conn;
            return (string)cmd.ExecuteScalar();
        }

        // CWE-22: путь от пользователя подставляется в File.ReadAllText без
        // проверки, что он остался внутри _root. "../../Windows/win.ini" проходит.
        public string ReadFileBadPath(string relative)
        {
            return File.ReadAllText(Path.Combine(_root, relative));
        }

        // CWE-327: MD5 для пароля. Здесь хотя бы с солью, но сама функция уже
        // не подходит: её перебирают сотнями миллионов хэшей в секунду.
        public string HashPasswordBad(string password)
        {
            using var md5 = MD5.Create();
            return Convert.ToHexString(md5.ComputeHash(System.Text.Encoding.UTF8.GetBytes(password)));
        }

        // CWE-78: пользовательский ввод уходит в командную строку оболочки.
        public void ZipBad(string folder)
        {
            var p = new Process();
            p.StartInfo.FileName = "cmd.exe";
            p.StartInfo.Arguments = "/c zip -r out.zip " + folder;
            p.Start();
            p.WaitForExit();
        }

        // CWE-502: десериализация произвольного типа из потока. Если файл
        // подменит злоумышленник, выполняется чужой код.
        public object ImportBad(Stream input)
        {
            return new BinaryFormatter().Deserialize(input);
        }

        // CWE-330: токен восстановления на системном Random со случайным seed.
        // Предсказуем, его можно восстановить по времени запроса.
        public string ResetTokenBad()
        {
            return new Random().Next(100000, 999999).ToString();
        }
    }
}
