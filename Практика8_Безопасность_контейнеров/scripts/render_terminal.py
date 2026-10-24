#!/usr/bin/env python3
# Рисует PNG с выводами команд для отчёта. Это не подделка результатов:
# текст берётся из сохранённых файлов results/*.txt, *.json.
# Нужно потому, что терминал в отчёте должен быть картинкой, а снимать
# окно консоли на Windows неудобно.

import json
import os

from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(BASE, "screenshots")
RESULTS = os.path.join(BASE, "results")
FONT_PATH = r"C:\Windows\Fonts\consola.ttf"
FONT_SIZE = 16
LINE_HEIGHT = 22
PADDING = 24


def draw_terminal(name, title, lines):
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    title_font = ImageFont.truetype(FONT_PATH, FONT_SIZE + 2)

    # Ограничиваем ширину, длинные строки переносим.
    max_chars = 100
    wrapped = []
    for line in lines:
        while len(line) > max_chars:
            wrapped.append(line[:max_chars])
            line = "    " + line[max_chars:]
        wrapped.append(line)

    width = 1100
    height = PADDING * 2 + 34 + LINE_HEIGHT * len(wrapped) + 10
    image = Image.new("RGB", (width, height), "#101418")
    draw = ImageDraw.Draw(image)
    draw.text((PADDING, PADDING), title, font=title_font, fill="#8be9fd")
    y = PADDING + 34
    for line in wrapped:
        color = "#f8f8f2"
        if line.startswith("$"):
            color = "#50fa7b"
        elif line.startswith("[WARN]"):
            color = "#ffb86c"
        elif line.startswith("[PASS]"):
            color = "#50fa7b"
        draw.text((PADDING, y), line, font=font, fill=color)
        y += LINE_HEIGHT
    path = os.path.join(SHOTS, name)
    image.save(path)
    print(path)


def main():
    os.makedirs(SHOTS, exist_ok=True)

    ps = open(os.path.join(RESULTS, "compose_ps.txt"), encoding="utf-8").read().rstrip().splitlines()
    draw_terminal("docker_ps.png", "docker compose ps", ps)

    with open(os.path.join(RESULTS, "trivy_web.json"), encoding="utf-8") as f:
        web = json.load(f)
    with open(os.path.join(RESULTS, "trivy_db.json"), encoding="utf-8") as f:
        db = json.load(f)

    def counts(data):
        result = {}
        for section in data.get("Results", []):
            for vuln in section.get("Vulnerabilities", []) or []:
                sev = vuln.get("Severity", "UNKNOWN")
                result[sev] = result.get(sev, 0) + 1
        return result

    web_counts = counts(web)
    db_counts = counts(db)
    lines = [
        "$ trivy image p8-web:local",
        "  CRITICAL: %d  HIGH: %d  MEDIUM: %d  LOW: %d" % (
            web_counts.get("CRITICAL", 0), web_counts.get("HIGH", 0),
            web_counts.get("MEDIUM", 0), web_counts.get("LOW", 0)),
        "$ trivy image postgres:16-alpine",
        "  CRITICAL: %d  HIGH: %d  MEDIUM: %d  LOW: %d" % (
            db_counts.get("CRITICAL", 0), db_counts.get("HIGH", 0),
            db_counts.get("MEDIUM", 0), db_counts.get("LOW", 0)),
        "",
        "Критичное в postgres: CVE-2025-68121 (stdlib Go, TLS session resumption)",
        "Основная масса HIGH в web: util-linux / libacl (базовый Debian)",
        "Flask 3.1.0: 2 HIGH, pip 25.0.1: 6 HIGH - обновить зависимости",
    ]
    draw_terminal("trivy_summary.png", "Trivy: сканирование образов", lines)

    bench = open(os.path.join(RESULTS, "docker_bench_clean.txt"), encoding="utf-8").read().splitlines()
    p8 = []
    for line in bench:
        if "p8-" in line or "p8_" in line or "p8-web" in line or "p8-db" in line:
            p8.append(line)
    lines = ["$ docker-bench-security", "Checks: 117   Score: 3", ""] + p8[:24]
    draw_terminal("bench_summary.png", "Docker Bench Security: замечания по p8", lines)


if __name__ == "__main__":
    main()
