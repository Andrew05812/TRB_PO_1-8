/*
 * Вариант 3 (номер студенческого билета заканчивается на 9).
 *
 * Исходный код из методички. Программа читает файл с «секретом» в буфер,
 * но затем передаёт argv[1] прямо в printf() как строку формата.
 * Это классическая format string vulnerability (CWE-134): пользователь
 * управляет не данными, а самим форматом вывода.
 *
 * Компилируется намеренно без защиты стека и без PIE, чтобы в отладчике
 * были видны фиксированные адреса:
 *   gcc -m32 -g -O0 -fno-stack-protector -no-pie -o vuln vuln_variant3.c
 */

#include <stdio.h>
#include <unistd.h>

int main(int argc, char *argv[])
{
    // В учебном контейнере файл создаётся заранее. В исходнике проверки
    // результата fopen нет: если файла не будет, fgets получит NULL.
    FILE *secret = fopen("/challenge/app-systeme/ch5/.passwd", "rt");
    char buffer[32];

    fgets(buffer, sizeof(buffer), secret);

    // Ошибка здесь: argv[1] - это данные, но printf воспринимает их как
    // строку формата. Спецификаторы %p, %s и %n начинают работать не так,
    // как задумывал автор программы.
    printf(argv[1]);

    fclose(secret);
    return 0;
}
