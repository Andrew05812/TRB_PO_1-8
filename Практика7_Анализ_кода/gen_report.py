#!/usr/bin/env python3
# Собирает отчёт по практике 7 в PDF.
# Сверху идёт страница из BAD_SIZEOF.pdf с предупреждением Svace,
# снизу - решение и комментарий. Промежуточный docx удаляется.

import os
import subprocess

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DOCX = os.path.join(BASE, "БСБО-03-23_Колесников_BAD_SIZEOF.docx")
OUT_PDF = os.path.join(BASE, "БСБО-03-23_Колесников_BAD_SIZEOF.pdf")
IMAGE = os.path.join(BASE, "source", "bad_sizeof_page3.png")

doc = Document()
section = doc.sections[0]
section.top_margin = Cm(1.5)
section.bottom_margin = Cm(1.5)
section.left_margin = Cm(1.8)
section.right_margin = Cm(1.5)

style = doc.styles["Normal"]
style.font.name = "Times New Roman"
style.font.size = Pt(11)


def para(text, bold=False, size=11, align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=4):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    return p


para("Практика 7. Анализ предупреждения статического анализатора",
     bold=True, size=14, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
para("Файл: BAD_SIZEOF.pdf, проект server, snapshot 2024-03-26",
     size=10, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)

# Исходная страница отчёта Svace: именно её разбираем.
doc.add_picture(IMAGE, width=Cm(13.4))
doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

para("Решение по файлу: Won't fix (ложное срабатывание)", bold=True, size=12,
     align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)

para("Колесников Андрей Юрьевич, 4 курс, группа БСБО-03-23",
     bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
para("Студенческий билет 23Б0099, номер по журналу 10",
     bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)

para("Комментарий", bold=True, size=12, space_after=4)

para(
    "Предупреждение BAD_SIZEOF в точке /server/sql/lock.cc:802 относится к строке "
    "sizeof(table_ptr) * table_count. Формально Svace прав: table_ptr — это параметр "
    "функции с типом TABLE **, поэтому sizeof(table_ptr) возвращает размер указателя "
    "(8 байт на x86_64), а не размер структуры TABLE. Однако в данном выражении "
    "выделяется память под массив указателей TABLE*, а не под массив структур. "
    "Размер элемента такого массива — тоже указатель, и на целевой платформе "
    "sizeof(TABLE*) совпадает с sizeof(TABLE**). Поэтому amount вычисляется верно, "
    "недостатка памяти и переполнения кучи здесь нет."
)
para(
    "Предупреждение возникло из-за того, что анализатор видит изолированный sizeof "
    "от параметра-указателя и не учитывает, что рядом выделяется массив указателей. "
    "Это контекстно-зависимый случай: если бы table_ptr имел тип TABLE* и массив "
    "состоял из структур TABLE, тогда sizeof(table_ptr) действительно привёл бы к "
    "недостаточного выделения памяти и переполнению. В текущем коде этого нет."
)
para(
    "Эксплуатация невозможна: значение table_count не влияет на размер элемента, "
    "выделение соответствует дальнейшему копированию массива указателей. Отмечаю "
    "только стилистическую рекомендацию: заменить sizeof(table_ptr) на "
    "sizeof(*table_ptr) — результат тот же, но намерение видно сразу и код не будет "
    "ломаться при будущем изменении типа параметра. Это не исправление уязвимости, "
    "поэтому статус файла — Won't fix."
)
para(
    "Второе срабатывание в этом же файле, /server/sql/sql_acl.cc:9933, относится к "
    "другому участку: там sizeof(buff) для параметра char * действительно даёт 8, а "
    "не размер буфера. Оно не входит в выбранную точку lock.cc:802 и требует "
    "отдельного разбора; в отчёте по взятому участку оно не учитывается."
)
para(
    "Итог: предупреждение в lock.cc:802 — ложное срабатывание, ошибки памяти нет. "
    "Решение: Won't fix, с комментарием о желательной замене на sizeof(*table_ptr) "
    "для читаемости.",
     bold=True,
)

doc.save(OUT_DOCX)

# LibreOffice установлен на машине; конвертируем в PDF и оставляем docx для правок.
subprocess.run(
    [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        BASE,
        OUT_DOCX,
    ],
    check=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
# Оставляем docx рядом с PDF: по заданию нужен PDF, но Word тоже полезен
# для правок перед защитой.
print("DOCX:", OUT_DOCX)
print("PDF:", OUT_PDF)
