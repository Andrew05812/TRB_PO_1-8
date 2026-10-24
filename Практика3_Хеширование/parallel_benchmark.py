#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Замер ускорения переборщика от числа процессов.

Отдельный скрипт, чтобы не мешать обычному запуску bruteforce.py. Здесь
специально берутся заведомо «неправильные» цели: хэши паролей, которых нет
в перебираемом множестве. Так каждый замер честно проходит весь объём
кандидатов, а не обрывается на первом же совпадении.

Что замеряем:
  - MD5, маска ?d?d?d?d?d?d — 1 000 000 вариантов;
  - bcrypt, словарь из wordlist.txt — 241 слово (сложный хэш из методички,
    которого в словаре нет);
  - Argon2id, тот же словарь и тот же сложный хэш.

Для каждого алгоритма запускаем 1, 2, 4 и 8 процессов и считаем ускорение
относительно одного процесса. Результат пишется в parallel_results.csv.
"""

import csv
import hashlib
import sys

from bruteforce import (
    LAB_HASHES,
    crack,
    default_chunk_size,
    fmt_seconds,
    iter_dictionary,
    iter_mask,
)

WORKERS = [1, 2, 4, 8]


def get_hard_hash(algorithm: str) -> str:
    return next(h for a, c, h in LAB_HASHES if a == algorithm and c == "сложный")


def run_case(algorithm: str, target: str, attack: str, make_candidates,
             max_candidates: int, workers: int):
    result = crack(
        make_candidates(),
        algorithm,
        target,
        workers=workers,
        chunk_size=default_chunk_size(algorithm),
        max_candidates=max_candidates,
        quiet=True,
    )
    # Пароля тут быть не должно: цели подобраны так, чтобы их не было
    # в перебираемом множестве. Если вдруг нашёлся — значит, ошибка в тесте.
    if result.found:
        raise RuntimeError(f"Неожиданно найден пароль {result.found!r} в замере {algorithm}")
    return result


def main() -> int:
    # Для MD5 берём хэш строки, которой точно нет среди шестизначных цифр.
    # Так маска отработает все 1 000 000 вариантов до конца.
    md5_target = hashlib.md5(b"zzzzzz").hexdigest()
    bcrypt_target = get_hard_hash("bcrypt")
    argon_target = get_hard_hash("argon2")

    cases = [
        ("md5", md5_target, "mask ?d?d?d?d?d?d",
         lambda: iter_mask("?d?d?d?d?d?d"), 1_000_000),
        ("bcrypt", bcrypt_target, "dict wordlist.txt",
         lambda: iter_dictionary("wordlist.txt"), 0),
        ("argon2", argon_target, "dict wordlist.txt",
         lambda: iter_dictionary("wordlist.txt"), 0),
    ]

    rows = []
    for algorithm, target, attack, make_candidates, max_candidates in cases:
        base_rate = None
        print(f"\n{algorithm.upper()}: {attack}")
        print(f"{'проц.':>6} {'время':>12} {'кандидатов':>12} {'хэш/с':>12} {'ускорение':>10}")
        print("-" * 58)

        for workers in WORKERS:
            result = run_case(algorithm, target, attack, make_candidates,
                              max_candidates, workers)
            rate = result.tried / result.elapsed if result.elapsed > 0 else 0
            if base_rate is None:
                base_rate = rate
            speedup = rate / base_rate if base_rate else 0
            print(f"{workers:>6} {fmt_seconds(result.elapsed):>12} "
                  f"{result.tried:>12,} {rate:>12,.0f} {speedup:>9.2f}x".replace(",", " "))
            rows.append({
                "algorithm": algorithm,
                "attack": attack,
                "workers": workers,
                "candidates": result.tried,
                "elapsed_seconds": f"{result.elapsed:.4f}",
                "hashes_per_second": f"{rate:.1f}",
                "speedup": f"{speedup:.2f}",
            })

    with open("parallel_results.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["algorithm", "attack", "workers",
                                               "candidates", "elapsed_seconds",
                                               "hashes_per_second", "speedup"])
        writer.writeheader()
        writer.writerows(rows)

    print("\nРезультаты сохранены в parallel_results.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
