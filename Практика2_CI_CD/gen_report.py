# -*- coding: utf-8 -*-
"""Собирает Отчет_Практика2.docx и PDF по практики 2."""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_tools"))
from docx_helper import add_heading, add_paragraph, add_table, add_title, new_document

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    doc = new_document()

    add_title(doc, "Отчёт по практике 2")
    add_title(doc, "Настройка локального CI/CD для FileManagerApp")
    add_paragraph(doc, "", indent=False)
    add_paragraph(doc, "Выполнил: Колесников Андрей Юрьевич, 4 курс, группа БСБО-03-23, "
                       "студенческий билет 23Б0099, номер по журналу 10",
                  center=True, indent=False)
    add_paragraph(doc, "РТУ МИРЭА, Институт кибербезопасности и цифровых технологий",
                  center=True, indent=False)

    add_heading(doc, "1. Цель работы")
    add_paragraph(doc,
        "Требовалось собрать локальный конвейер CI/CD для приложения из практики 1. "
        "Все шаги должны идти в изолированных Docker-контейнерах, чтобы версия .NET "
        "на хосте не влияла на результат. В конвейере нужны сборка, тесты с отчётом "
        "JUnit, SAST с остановкой на критических находках и локальный деплой. "
        "Отдельно проверяются кэш зависимостей, артефакты между стадиями, "
        "непривилегированный пользователь в образе и отсутствие секретов в YAML.")

    add_heading(doc, "2. Стенд")
    add_paragraph(doc,
        "Конвейер рассчитан на GitLab CI и Docker-executor. Файл .gitlab-ci.yml "
        "лежит в папке практики, Dockerfile собирает приложение из FileManagerApp. "
        "Локально доступны Docker 29.8.1 и .NET SDK 8; сам сервер GitLab с раннером "
        "не поднимался, стадии проверены теми же командами, что записаны в конфиге. "
        "Это ограничение указано и в README, и в выводах.")
    add_table(doc, ["Компонент", "Значение"], [
        ["Приложение", "FileManagerApp, .NET 8, консольное"],
        ["Базовый образ сборки", "mcr.microsoft.com/dotnet/sdk:8.0"],
        ["Финальный образ", "mcr.microsoft.com/dotnet/runtime:8.0 + libsqlite3-0"],
        ["Размер образа", "около 288 МБ"],
        ["Пользователь", "appuser, uid 10001"],
        ["CI", "GitLab CI, четыре стадии"],
    ])

    add_heading(doc, "2.1. Соответствие требованиям", level=2)
    add_table(doc, ["Требование задания", "Где реализовано", "Чем подтверждается"], [
        ["Изолированные Docker-контейнеры",
         "образы sdk/runtime, docker:24.0", "build/test/sast/deploy идут в контейнерах"],
        ["Стадия build", "build_app", "dotnet restore + publish в Release"],
        ["Стадия test с JUnit", "run_tests", "18 testcase, failures=0"],
        ["Стадия SAST", "security_scan", "Semgrep, --severity ERROR --error"],
        ["Стадия local deploy", "local_deploy", "docker build + docker run --selfcheck"],
        ["Кэш зависимостей", "cache: .nuget/packages", "ключ nuget-cache"],
        ["Артефакты между стадиями", "artifacts: publish/", "test забирает publish через dependencies"],
        ["Multi-stage Dockerfile", "Dockerfile", "SDK остаётся только в builder"],
        ["Непривилегированный пользователь", "USER appuser, uid 10001", "запуск образа"],
        ["Секреты не в коде", "CI/CD variables, README", "в YAML токенов нет"],
    ])

    add_heading(doc, "3. Dockerfile")
    add_paragraph(doc,
        "Dockerfile многоступенчатый. На первом этапе SDK восстанавливает зависимости "
        "и публикует приложение в Release. На втором остаётся только runtime, "
        "библиотека SQLite и опубликованные файлы; SDK, исходники и кэш NuGet в "
        "финальный образ не попадают. Создаётся пользователь appuser с uid 10001, "
        "и USER переключает контейнер на него. Это уменьшает последствия ошибки в "
        "приложении: процесс не работает от root.")
    add_paragraph(doc,
        "Для SQLite в runtime-образ ставится libsqlite3-0. Приложение запускается "
        "командой dotnet FileManagerApp.dll; при старте без аргументов открывается "
        "меню, а с --selfcheck выполняются 18 проверок. В контейнере проверка "
        "проходит, код возврата 0.")

    add_heading(doc, "4. Стадии конвейера")
    add_table(doc, ["Стадия", "Что делает", "Артефакт / кэш"], [
        ["build", "restore и publish в Release", "publish/, кэш NuGet"],
        ["test", "запускает --selfcheck и превращает OK в JUnit XML", "test-results.xml"],
        ["sast", "Semgrep по исходникам, --severity ERROR --error", "логи и находки"],
        ["deploy", "docker build и docker run --selfcheck", "локальный образ"],
    ])
    add_paragraph(doc,
        "Кэш NuGet вынесен в .nuget/packages и привязан ключом nuget-cache, "
        "поэтому повторная сборка не скачивает пакеты заново. publish/ передаётся "
        "из build в test через dependencies; JUnit-отчёт публикуется в "
        "artifacts.reports.junit, чтобы GitLab показывал тесты во вкладке Tests. "
        "Semgrep запускается после cd в папку приложения, потому что кириллический "
        "путь он не принимает как корень сканирования. У джобы стоит "
        "entrypoint: [\"\"]: иначе образ semgrep/semgrep передаёт cd в сам "
        "сканер.")
    add_paragraph(doc,
        "Деплой использует docker:24.0 и сервис docker:24.0-dind. Переменные "
        "DOCKER_HOST=tcp://docker:2375 и DOCKER_TLS_CERTDIR=\"\" направляют "
        "клиент на дочерний демон. Порт не пробрасывается: приложение консольное, "
        "HTTP-сервера у него нет. Вместо проверки порта контейнер запускается с "
        "--selfcheck и проверяется код возврата; для веб-приложения здесь было бы "
        "docker run -d -p 8080:8080.")

    add_heading(doc, "5. Проверка")
    add_paragraph(doc,
        "Публикация и JUnit:")
    add_paragraph(doc,
        "dotnet publish -c Release -o publish\n"
        "bash \"Практика2_CI_CD/scripts/run_selfcheck_as_junit.sh\" "
        "publish/FileManagerApp.dll test-results.xml", indent=False)
    add_paragraph(doc,
        "В XML получилось tests=\"18\" failures=\"0\" errors=\"0\". Скрипт разбирает "
        "строки OK: и делает по каждой отдельный <testcase>; если самопроверка "
        "падает, он завершает работу с ненулевым кодом.")
    add_paragraph(doc,
        "Сборка и запуск образа:")
    add_paragraph(doc,
        "docker build -t filemanagerapp:local -f Практика2_CI_CD/Dockerfile .\n"
        "docker run --rm filemanagerapp:local --selfcheck", indent=False)
    add_paragraph(doc,
        "Образ собрался, размер около 288 МБ, контейнер вернул 0. Semgrep по 13 "
        "исходным файлам не нашёл ошибок уровня ERROR. Полноценный GitLab-раннер не "
        "запускался: это единственное, что проверено локально, а не в веб-интерфейсе "
        "GitLab.")

    add_heading(doc, "6. Секреты и риски")
    add_paragraph(doc,
        "В .gitlab-ci.yml нет токенов и паролей. Для приватного registry "
        "предусмотрены masked/protected variables CI_REGISTRY_USER и "
        "CI_REGISTRY_PASSWORD; локально они задаются переменными окружения. "
        "Проброс docker.sock и --docker-privileged допустимы только на учебной "
        "машине: они дают джобе большой контроль над хостом. В продакшене нужен "
        "отдельный изолированный runner и минимальные права.")

    add_heading(doc, "7. Ограничения и выводы")
    add_paragraph(doc,
        "Полный сервер GitLab и раннер не разворачивались; стадии проверены "
        "локальными командами, идентичными конфигу. Это позволяет проверить сборку, "
        "тесты, SAST и образ, но не проверяет поведение самого GitLab (очередь, "
        "переменные, UI). Для учебной работы этого достаточно, и ограничение "
        "отражено в README.")
    add_paragraph(doc,
        "В итоге конвейер закрывает все пункты задания: изолированные контейнеры, "
        "build, тесты с JUnit, SAST с падением на ERROR, кэш NuGet, артефакты между "
        "стадиями и локальный деплой. Dockerfile многоступенчатый, приложение "
        "работает от непривилегированного пользователя, секретов в конфиге нет.")

    out_docx = os.path.join(BASE, "Отчет_Практика2.docx")
    doc.save(out_docx)
    subprocess.run([
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        "--headless", "--convert-to", "pdf", "--outdir", BASE, out_docx,
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(out_docx)
    print(os.path.join(BASE, "Отчет_Практика2.pdf"))


if __name__ == "__main__":
    main()
