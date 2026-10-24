#!/usr/bin/env bash
# Сравнение собственного переборщика с John the Ripper jumbo.
#
# John запускается в Docker, потому что под Windows его нормально не поставить.
# Образ собирается из john/Dockerfile: готовый образ из Docker Hub оказался
# старым и не понимал $argon2id$.
#
# Для каждого алгоритма берётся тот же словарь wordlist.txt и те же четыре
# хэша из методички. В CSV пишутся два времени: elapsed_seconds — внутреннее
# время John из его строки DONE (его и надо сравнивать с bruteforce.py),
# docker_wall_seconds — полное время с запуском контейнера, оно нужно только
# чтобы показать накладные расходы Docker и в сравнении не участвует.

set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd -W 2>/dev/null || pwd)"

if ! docker image inspect john-jumbo-lab >/dev/null 2>&1; then
    echo "Собираю образ john-jumbo-lab (один раз, это долго)..."
    docker build -t john-jumbo-lab john
fi

mkdir -p john/pot john
rm -f john/pot/*.pot john/pot/*.rec
: > john/john_results.csv
echo "algorithm,format,hashes,cracked,elapsed_seconds,docker_wall_seconds,threads,cracked_list" >> john/john_results.csv

run_one() {
    local name="$1"      # sha1 / md5 / bcrypt / argon2
    local format="$2"    # имя формата в John
    local file="$3"      # файл с хэшами
    local label="$4"     # человеческое название для вывода

    local start end wall elapsed
    start=$(date +%s%N)

    docker run --rm \
        -v "$ROOT:/data" \
        john-jumbo-lab \
        --format="$format" \
        --wordlist=/data/wordlist.txt \
        --pot="/data/john/pot/$name.pot" \
        --session="/data/john/pot/$name" \
        "/data/$file" > "john/${name}.log" 2>&1 || true

    end=$(date +%s%N)
    wall=$(awk -v s="$start" -v e="$end" 'BEGIN { printf "%.3f", (e - s) / 1000000000 }')

    # Внутреннее время John: строка вида "0:00:00:05 DONE" — это
    # дни:часы:минуты:секунды. Для быстрых форматов там 0:00:00:00,
    # то есть меньше секунды; так и пишем в CSV.
    elapsed=$(grep -oE '[0-9]+:[0-9]{2}:[0-9]{2}:[0-9]{2} DONE' "john/${name}.log" | head -1 | awk -F'[: ]' '{ printf "%.3f", $1*86400 + $2*3600 + $3*60 + $4 }' || true)
    elapsed=${elapsed:-0}

    # Отдельным запуском просим John показать, что он в итоге подобрал.
    # Пот-файл лежит на хосте, поэтому результаты не теряются между контейнерами.
    docker run --rm \
        -v "$ROOT:/data" \
        john-jumbo-lab \
        --show --format="$format" --pot="/data/john/pot/$name.pot" \
        "/data/$file" > "john/${name}_show.log" 2>&1 || true

    local cracked threads cracked_list
    cracked=$(grep -oE '^[0-9]+ password hashes cracked' "john/${name}_show.log" | awk '{print $1}' | head -1 || true)
    cracked=${cracked:-0}
    threads=$(grep -oE 'Will run [0-9]+ OpenMP threads' "john/${name}.log" | grep -oE '[0-9]+' | head -1 || true)
    threads=${threads:-1}
    cracked_list=$(sed -n 's/^[^:]*://p' "john/${name}_show.log" | paste -sd ';' - || true)

    printf "%-8s %-9s  хэшей: 4, найдено: %s, время John: %s с (с Docker: %s с), потоков: %s\n" \
        "$label" "$format" "$cracked" "$elapsed" "$wall" "$threads"
    if [ -n "$cracked_list" ]; then
        printf "         пароли: %s\n" "$cracked_list"
    fi

    echo "$label,$format,4,$cracked,$elapsed,$wall,$threads,$cracked_list" >> john/john_results.csv
}

run_one sha1   Raw-SHA1 john/hashes_sha1.txt   SHA-1
run_one md5    Raw-MD5  john/hashes_md5.txt    MD5
run_one bcrypt bcrypt   john/hashes_bcrypt.txt bcrypt
run_one argon2 argon2   john/hashes_argon2.txt Argon2id

echo
echo "Результаты: john/john_results.csv"
