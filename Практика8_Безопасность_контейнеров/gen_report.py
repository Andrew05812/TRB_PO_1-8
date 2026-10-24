# -*- coding: utf-8 -*-
"""Собирает Отчет_Практика8.docx по результатам docker compose, Trivy и Docker Bench."""

import json
import os
import sys

from docx.shared import Cm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_tools"))
from docx_helper import add_heading, add_paragraph, add_table, add_title, new_document, save_docx_and_pdf

BASE = os.path.dirname(os.path.abspath(__file__))


def trivy_counts(name):
    with open(os.path.join(BASE, "results", f"trivy_{name}.json"), encoding="utf-8") as f:
        data = json.load(f)
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
    for section in data.get("Results", []):
        for vuln in section.get("Vulnerabilities", []) or []:
            sev = vuln.get("Severity", "UNKNOWN")
            counts[sev] = counts.get(sev, 0) + 1
    return counts


def main():
    web = trivy_counts("web")
    db = trivy_counts("db")

    doc = new_document()

    add_title(doc, "Отчёт по практике 8")
    add_title(doc, "Безопасность контейнеров: веб-приложение, база данных и сканирование")
    add_paragraph(doc, "", indent=False)
    add_paragraph(doc, "Выполнил: Колесников Андрей Юрьевич, 4 курс, группа БСБО-03-23, "
                       "студенческий билет 23Б0099, номер по журналу 10", center=True, indent=False)
    add_paragraph(doc, "РТУ МИРЭА, Институт кибербезопасности и цифровых технологий",
                  center=True, indent=False)

    add_heading(doc, "1. Что требовалось")
    add_paragraph(doc,
        "Нужно было развернуть веб-сайт с базой данных, настроить постоянное "
        "хранение и отдельное сетевое окружение, а затем проверить контейнер и образ "
        "средствами безопасности. В отчёте требуется привести скриншоты, разобрать "
        "вывод сканеров и предложить меры по устранению находок.")

    add_heading(doc, "2. Архитектура стенда")
    add_paragraph(doc,
        "Стенд состоит из двух контейнеров. p8-web — Flask-приложение на Python 3.12, "
        "которое отдаёт страницу со списком объектов и обращается к PostgreSQL. "
        "p8-db — официальный postgres:16-alpine. Приложение опубликовано только на "
        "127.0.0.1:8088; база не публикует порт наружу и доступна приложению по имени "
        "db внутри пользовательской bridge-сети p8_backend. Данные лежат в именованном "
        "томе p8_pgdata, поэтому переживают пересоздание контейнеров.")
    add_paragraph(doc,
        "Секреты не зашиты в Dockerfile: пароль базы передаётся через .env (в репозиторий "
        "попадает только .env.example) и переменную DATABASE_URL. Для учебного стенда "
        "пароль фиксированный, для реального его нужно генерировать и хранить в "
        "Docker secrets или другом хранилище.")

    add_table(doc, ["Компонент", "Образ / параметры", "Назначение"], [
        ["p8-web", "p8-web:local, 198 МБ, uid 10001", "Flask + gunicorn, страница объектов"],
        ["p8-db", "postgres:16-alpine, 420 МБ", "PostgreSQL, том p8_pgdata"],
        ["Сеть", "p8_backend, bridge", "изоляция от default bridge"],
        ["Порт", "127.0.0.1:8088 → 8080", "доступ только с хоста"],
        ["Том", "p8_pgdata", "постоянное хранение данных"],
    ])
    doc.add_picture(os.path.join(BASE, "screenshots", "app.png"), width=Cm(15.5))
    doc.paragraphs[-1].alignment = 1
    add_paragraph(doc, "Скриншот страницы: данные приходят из PostgreSQL, счётчик "
                       "просмотров увеличивается при каждом обновлении.", center=True, indent=False)

    add_heading(doc, "3. Запуск и проверка")
    add_paragraph(doc, "Последовательность запуска:")
    add_paragraph(doc,
        "copy .env.example .env\n"
        "docker compose up -d --build\n"
        "docker compose ps\n"
        "curl http://127.0.0.1:8088/", indent=False)
    add_paragraph(doc,
        "Оба контейнера переходят в состояние healthy. Приложение проверено запросом "
        "к / и к /healthz, база — через healthcheck pg_isready. На скриншоте ниже — "
        "фактический вывод docker compose ps.")
    doc.add_picture(os.path.join(BASE, "screenshots", "docker_ps.png"), width=Cm(16))
    doc.paragraphs[-1].alignment = 1

    add_paragraph(doc,
        "Постоянное хранение проверено так: до перезапуска счётчик показывал 3 "
        "просмотра, после docker compose restart — 4, после docker compose down и "
        "up без удаления тома — 5. Данные и схема остались на месте, потому что том "
        "p8_pgdata не удалялся. Команда docker compose down -v удалила бы том и "
        "обнулила базу — это ожидаемое поведение, но в отчёте важно не перепутать "
        "down и down -v.")

    doc.add_picture(os.path.join(BASE, "screenshots", "storage_network.png"), width=Cm(16))
    doc.paragraphs[-1].alignment = 1
    add_paragraph(doc,
        "Том p8_pgdata и сеть p8_backend: база и приложение находятся в одной "
        "пользовательской bridge-сети, том смонтирован в /var/lib/postgresql/data.",
        center=True, indent=False)

    add_heading(doc, "4. Настройки безопасности контейнеров")
    add_table(doc, ["Мера", "Где", "Зачем"], [
        ["Непривилегированный пользователь", "Dockerfile, USER 10001", "приложение не root"],
        ["read-only корневая ФС", "web и db", "нельзя дописать файлы в образ"],
        ["tmpfs /tmp", "web", "gunicorn может писать временные файлы"],
        ["cap_drop: ALL", "web", "убирает лишние capabilities"],
        ["no-new-privileges", "web и db", "запрещает повышение привилегий"],
        ["Лимиты CPU/памяти/PIDs", "compose", "защита от исчерпания ресурсов"],
        ["Порт только на 127.0.0.1", "web", "сайт не доступен всей сети"],
        ["Отдельная сеть", "p8_backend", "нет доступа к default bridge"],
        ["HEALTHCHECK", "Dockerfile и compose", "видно, что сервис жив"],
    ])
    add_paragraph(doc,
        "Отдельно про базу: официальный postgres при первом старте запускается от root, "
        "чтобы выставить владельца каталога данных, а затем сам сбрасывает права на "
        "пользователя postgres. Поэтому в Docker Bench он отмечен как «Running as root». "
        "Это особенность официального образа, а не приложения; на реальном стенде "
        "лучше использовать заранее подготовленный том и запуск от uid postgres.")

    add_heading(doc, "5. Trivy: сканирование образов")
    add_paragraph(doc,
        "Образы сохранены в tar и просканированы Trivy без доступа к Docker-сокету:")
    add_paragraph(doc,
        "docker save p8-web:local -o p8-web.tar\n"
        "docker run --rm -v \"${PWD}:/work\" aquasec/trivy image --input /work/p8-web.tar", indent=False)
    add_table(doc, ["Образ", "CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN", "Всего"], [
        ["p8-web:local", str(web["CRITICAL"]), str(web["HIGH"]), str(web["MEDIUM"]),
         str(web["LOW"]), str(web["UNKNOWN"]), str(sum(web.values()))],
        ["postgres:16-alpine", str(db["CRITICAL"]), str(db["HIGH"]), str(db["MEDIUM"]),
         str(db["LOW"]), str(db["UNKNOWN"]), str(sum(db.values()))],
    ])
    doc.add_picture(os.path.join(BASE, "screenshots", "trivy_summary.png"), width=Cm(16))
    doc.paragraphs[-1].alignment = 1

    add_paragraph(doc,
        "В p8-web основная масса HIGH приходится на базовый Debian: util-linux, libacl "
        "и другие системные пакеты. Из прикладных зависимостей выделяются Flask 3.1.0 "
        "(2 HIGH) и pip 25.0.1 (6 HIGH). В postgres:16-alpine один CRITICAL — "
        "CVE-2025-68121 в Go stdlib (crypto/tls, неправильная проверка сертификата при "
        "возобновлении TLS-сессии). База не публикует порт наружу, поэтому этот путь "
        "не доступен извне, но образ всё равно нужно обновлять.")
    add_paragraph(doc,
        "Быстрых «патчей в Dockerfile» здесь нет: часть уязвимостей без исправлений в "
        "текущем дистрибутиве. Правильные меры — пересобирать образ регулярно, "
        "перейти на более свежий базовый образ (slim-bookworm или distroless), "
        "обновить Flask и убрать pip из runtime-слоя, а также добавить Trivy в CI с "
        "порогом по CRITICAL/HIGH. Для postgres — обновлять тег и следить за "
        "релизами образа; критичный TLS-баг не влияет на текущую схему, пока база "
        "недоступна по сети.")

    add_heading(doc, "6. Docker Bench Security")
    add_paragraph(doc,
        "Docker Bench запущен из официального репозитория на хосте (в контейнере на "
        "Windows он не видит docker.sock). Проверок 117, итоговый score — 3. Много "
        "замечаний относится к самому Docker Desktop: аудит хоста, user namespaces, "
        "AppArmor и централизованный журнал на Windows не настроены. По стенду p8 "
        "после внесённых исправлений остались:")
    add_table(doc, ["Замечание", "Отношение к p8", "Что делать"], [
        ["Running as root: p8-db", "официальный postgres", "запускать от uid postgres после init"],
        ["No AppArmorProfile: p8-web/p8-db", "Docker Desktop", "включить AppArmor на Linux-хосте"],
        ["Port in use: 8088", "опубликован только loopback", "оставить, это нужный порт"],
        ["No Healthcheck found", "исправлено", "HEALTHCHECK добавлен в Dockerfile"],
        ["No CPU restrictions", "исправлено", "cpus: 0.50 в compose"],
        ["Root FS mounted R/W: p8-db", "исправлено", "read_only: true и tmpfs"],
    ])
    doc.add_picture(os.path.join(BASE, "screenshots", "bench_summary.png"), width=Cm(16))
    doc.paragraphs[-1].alignment = 1
    add_paragraph(doc,
        "На скриншоте уже финальный прогон: замечаний про healthcheck и CPU-лимиты "
        "там нет. В таблице они оставлены с пометкой «исправлено», чтобы было видно, "
        "что именно изменилось после первого сканирования. Полный текстовый вывод "
        "лежит в results/docker_bench_clean.txt.")

    add_heading(doc, "7. Что исправлено по итогам сканирования")
    add_paragraph(doc,
        "После первого прогона Docker Bench в образ добавлен HEALTHCHECK, в compose — "
        "лимиты CPU и read-only корневая ФС для базы с tmpfs для /tmp и "
        "/var/run/postgresql. Повторный прогон подтвердил, что замечания про "
        "healthcheck, CPU и R/W root для p8-db ушли. Остались только root-процесс "
        "postgres, отсутствие AppArmor на Docker Desktop и опубликованный loopback-порт.")
    add_paragraph(doc,
        "Дополнительные меры, которые имеет смысл сделать в реальном проекте: "
        "перейти на distroless или alpine-базу, убрать pip из финального слоя, "
        "подписать образ (cosign/DCT), включить сканирование Trivy в CI с блокировкой "
        "по CRITICAL, использовать Docker secrets вместо .env, настроить AppArmor и "
        "централизованный сбор логов, ограничить исходящие соединения контейнера.")

    add_heading(doc, "7.1. Соответствие требованиям", level=2)
    add_table(doc, ["Пункт задания", "Что сделано", "Где смотреть"], [
        ["Веб-сайт с базой данных",
         "Flask + PostgreSQL, таблица objects",
         "раздел 2, app/app.py, скриншот страницы"],
        ["Постоянное хранение",
         "именованный том p8_pgdata",
         "раздел 3, storage_network.png, тест restart/down-up"],
        ["Сетевое окружение",
         "bridge-сеть p8_backend, порт только на 127.0.0.1",
         "раздел 3, storage_network.png, docker compose ps"],
        ["Проверка образа",
         "Trivy: 175 находок web, 64 postgres",
         "раздел 5, trivy_web.txt/trivy_db.txt"],
        ["Проверка контейнера",
         "Docker Bench: 117 проверок, score 3",
         "раздел 6, docker_bench_clean.txt"],
        ["Скриншоты и последовательность",
         "страница, compose ps, том/сеть, Trivy, Bench",
         "разделы 2, 3, 5, 6"],
        ["Меры по исправлению",
         "обновление баз, Flask/pip, CI-порог, secrets, AppArmor",
         "раздел 7 и выводы"],
    ])

    add_heading(doc, "8. Выводы")
    add_paragraph(doc,
        "Стенд из веб-приложения и PostgreSQL развёрнут, данные лежат в именованном "
        "томе и переживают перезапуск, сеть изолирована, наружу открыт только "
        "loopback-порт. Контейнер приложения работает от uid 10001 с read-only "
        "корневой ФС, без capabilities и с no-new-privileges. Trivy нашёл 175 "
        "уязвимостей в p8-web и 64 в postgres, из них одна критическая в Go stdlib "
        "postgres; разобраны причины и предложены меры. Docker Bench дал 113 "
        "предупреждений по хосту и образу, по p8 после исправлений остались только "
        "объяснимые замечания.")
    add_paragraph(doc,
        "Главный вывод: сканеры показывают не «плохой/хороший контейнер», а набор "
        "компромиссов. Образ на официальной базе всё равно содержит десятки CVE, "
        "которые нельзя исправить в Dockerfile; помогает регулярная пересборка, "
        "минимизация образа и перенос проверок в CI. Ограничение работы — Docker "
        "Desktop на Windows, поэтому часть проверок хоста (AppArmor, аудит, "
        "user namespaces) недоступна и отмечена как среда, а не как дефект стенда.")

    out = os.path.join(BASE, "Отчет_Практика8.docx")
    save_docx_and_pdf(doc, out)
    print(out)


if __name__ == "__main__":
    main()
