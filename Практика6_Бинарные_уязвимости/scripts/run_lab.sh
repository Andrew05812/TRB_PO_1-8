#!/bin/sh
# Сборка и базовые запуски для практики 6. Выполняется внутри контейнера p6-lab.
set -eu

# В образе gcc:12 системный /usr/local/bin/gcc не умеет -m32,
# поэтому 32-битная сборка идёт через gcc-12 из Debian-пакета gcc-multilib.
gcc-12 -m32 -g -O0 -fno-stack-protector -no-pie -z execstack \
    -o build/vuln src/vuln_variant3.c
gcc-12 -m32 -g -O0 -fno-stack-protector -no-pie \
    -o build/fixed src/fixed_variant3.c
gcc-12 -m32 -g -O0 -fno-stack-protector -no-pie -z execstack \
    -o build/fmtwrite src/format_write_demo.c

echo "--- обычный запуск ---"
./build/vuln "hello"

echo
echo "--- утечка стека через %p ---"
./build/vuln "ARGV=%p argv2=%p stack3=%p stack4=%p stack5=%p stack6=%p stack7=%p stack8=%p"

echo
echo "--- исправленная версия: %p уже не команда ---"
./build/fixed "ARGV=%p argv2=%p %n"

echo
echo "--- запись через %n ---"
python3 scripts/find_offset.py
python3 scripts/write_demo.py
