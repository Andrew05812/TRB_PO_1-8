/*
 * Исправленный вариант 3.
 *
 * Отличие от уязвимой версии небольшое: строка формата теперь постоянная
 * ("%s"), а пользовательский ввод передаётся аргументом. Символы % в
 * argv[1] больше не воспринимаются как команды printf.
 *
 * Дополнительно добавлены проверки, которых не было в исходнике:
 *   - argc: без аргумента программа не обращается к argv[1];
 *   - fopen: если файл не открылся, fgets не вызывается с NULL;
 *   - fgets: проверяется результат чтения.
 * Эти проверки не «лечат» форматную строку, но убирают падения при
 * неправильном запуске.
 */

#include <stdio.h>
#include <unistd.h>

int main(int argc, char *argv[])
{
    if (argc != 2) {
        fprintf(stderr, "Использование: %s <строка>\n", argv[0]);
        return 2;
    }

    FILE *secret = fopen("/challenge/app-systeme/ch5/.passwd", "rt");
    if (secret == NULL) {
        perror("fopen");
        return 1;
    }

    char buffer[32];
    if (fgets(buffer, sizeof(buffer), secret) == NULL) {
        fclose(secret);
        return 1;
    }
    fclose(secret);

    // Безопасно: формат задан константой, ввод - просто данные.
    printf("%s\n", argv[1]);
    return 0;
}
