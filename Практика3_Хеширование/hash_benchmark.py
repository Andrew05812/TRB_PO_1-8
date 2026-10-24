#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Практика 3. Сравнение алгоритмов хеширования (SHA-1, MD5, bcrypt, Argon2)
Колесников А.Ю., БСБО-03-23, студ. билет 23Б0099

Этот скрипт измеряет стоимость ОДНОГО вычисления хэша и по ней считает
теоретическое время полного перебора. Он нужен для второй части отчёта:
получаются чистые цифры «хэшей в секунду» без накладных расходов на
генерацию кандидатов и межпроцессное взаимодействие.

Сам подбор паролей по хэшу делает bruteforce.py (словарь, маска,
многопроцессность), а сравнение с John the Ripper — run_john.sh.
Результаты всех трёх частей складываются в общий отчёт gen_report.py.
"""

import hashlib
import time
import csv
import sys

import bcrypt
from argon2.low_level import hash_secret_raw, Type


# ---------------------------------------------------------------------------
# Пароли для замера. Здесь важна не стойкость, а длина: скорость хэширования
# от самих символов почти не зависит, поэтому берём просто разные по длине
# строки. Реальные хэши из методички перебираются в bruteforce.py.
# ---------------------------------------------------------------------------
TEST_PASSWORDS = {
    "лёгкий (4 цифры)": "1234",
    "средний (8 симв.)": "qwerty12",
    "сложный (12 симв.)": "K7$mPz2!qLw9",
    "очень сложный (16 симв.)": "xT9#vQ2!mZp7$kR4",
}

# Параметры bcrypt и Argon2 взяты такими же, как в тестовых хэшах из
# методички ($2a$10$... и $argon2id$v=19$m=65536,t=3,p=2$...) - чтобы
# цифры из этого замера были сравнимы с тем, что дано в задании
BCRYPT_COST = 10
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST_KB = 65536  # 64 МБ
ARGON2_PARALLELISM = 2
ARGON2_HASH_LEN = 32

# Алфавит для теоретического расчёта keyspace (строчные+заглавные+цифры+
# немного спецсимволов - типичный "разрешённый" набор на большинстве сайтов)
CHARSET_SIZE = 26 + 26 + 10 + 10  # 72 символа


def self_test_sha1_md5():
    """Проверяем, что хэш-функции вызываются правильно: сверяем с
    общеизвестными эталонными значениями для строки 'abc'. Это не подбор,
    а обычная проверка перед замером, чтобы не мерить сломанный вызов."""
    sha1_abc = hashlib.sha1(b"abc").hexdigest()
    md5_abc = hashlib.md5(b"abc").hexdigest()

    assert sha1_abc == "a9993e364706816aba3e25717850c26c9cd0d89d", "SHA-1 эталонный тест не прошёл"
    assert md5_abc == "900150983cd24fb0d6963f7d28e17f72", "MD5 эталонный тест не прошёл"
    print("Самопроверка SHA-1/MD5 на эталонной строке 'abc' пройдена.\n")


def time_sha1(password: str, repeats: int = 200_000) -> float:
    """SHA-1 и MD5 слишком быстрые, чтобы мерить одно вычисление -
    погрешность таймера будет больше самого результата. Поэтому гоняем
    много повторов подряд и берём среднее на одно вычисление."""
    data = password.encode("utf-8")
    start = time.perf_counter()
    for _ in range(repeats):
        hashlib.sha1(data).digest()
    elapsed = time.perf_counter() - start
    return elapsed / repeats


def time_md5(password: str, repeats: int = 200_000) -> float:
    data = password.encode("utf-8")
    start = time.perf_counter()
    for _ in range(repeats):
        hashlib.md5(data).digest()
    elapsed = time.perf_counter() - start
    return elapsed / repeats


def time_bcrypt(password: str, repeats: int = 3) -> float:
    """bcrypt специально медленный, поэтому хватит пары повторов -
    берём среднее, чтобы сгладить случайные скачки (другие процессы на машине и т.п.)"""
    data = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=BCRYPT_COST)
    start = time.perf_counter()
    for _ in range(repeats):
        bcrypt.hashpw(data, salt)
    elapsed = time.perf_counter() - start
    return elapsed / repeats


def time_argon2(password: str, repeats: int = 3) -> float:
    data = password.encode("utf-8")
    salt = b"saltsalt"  # как в примере методички - там указано Salt = "saltsalt"
    start = time.perf_counter()
    for _ in range(repeats):
        hash_secret_raw(
            secret=data,
            salt=salt,
            time_cost=ARGON2_TIME_COST,
            memory_cost=ARGON2_MEMORY_COST_KB,
            parallelism=ARGON2_PARALLELISM,
            hash_len=ARGON2_HASH_LEN,
            type=Type.ID,
        )
    elapsed = time.perf_counter() - start
    return elapsed / repeats


def human_time(seconds: float) -> str:
    """Переводим секунды в читаемый вид - для больших чисел (годы перебора)
    это единственный способ вообще что-то понять в результате"""
    if seconds < 1:
        return f"{seconds * 1000:.3f} мс"
    units = [
        ("секунд", 1),
        ("минут", 60),
        ("часов", 3600),
        ("дней", 86400),
        ("лет", 365.25 * 86400),
    ]
    best_label, best_div = "секунд", 1
    for label, div in units:
        if seconds >= div:
            best_label, best_div = label, div
    value = seconds / best_div
    if best_div >= units[-1][1] and value > 1e6:
        return f"{value:.3e} {best_label}"
    return f"{value:,.2f} {best_label}".replace(",", " ")


def theoretical_bruteforce_time(seconds_per_hash: float, password_length: int) -> float:
    """Сколько бы ТЕОРЕТИЧЕСКИ заняло перебрать все пароли данной длины
    из алфавита CHARSET_SIZE символов при данной скорости хэширования.
    В среднем находят пароль за половину полного перебора, поэтому /2."""
    keyspace = CHARSET_SIZE ** password_length
    hashes_per_second = 1 / seconds_per_hash if seconds_per_hash > 0 else float("inf")
    return (keyspace / hashes_per_second) / 2


def main():
    self_test_sha1_md5()

    algorithms = {
        "SHA-1": time_sha1,
        "MD5": time_md5,
        "bcrypt (cost=10)": time_bcrypt,
        "Argon2id (m=64МБ,t=3,p=2)": time_argon2,
    }

    rows = []
    print(f"{'Алгоритм':<28} {'Пароль':<28} {'Время на 1 хэш':<18} {'Хэшей/сек':<14}")
    print("-" * 92)

    for algo_name, func in algorithms.items():
        for pass_label, password in TEST_PASSWORDS.items():
            t = func(password)
            rate = 1 / t if t > 0 else float("inf")
            print(f"{algo_name:<28} {pass_label:<28} {t * 1000:<18.6f} мс  {rate:,.1f}".replace(",", " "))
            rows.append({
                "algorithm": algo_name,
                "password_category": pass_label,
                "password_length": len(password),
                "seconds_per_hash": t,
                "hashes_per_second": rate,
            })
        print()

    # Теоретическая оценка полного перебора для пароля длиной 8 символов
    # (разумный ориентир - примерно столько требуют на многих сайтах)
    print("Теоретическое время полного перебора пароля из 8 символов")
    print(f"(алфавит из {CHARSET_SIZE} символов: a-z A-Z 0-9 + спецсимволы), по формуле keyspace / (2 * хэшей_в_секунду):\n")

    # берём среднюю скорость алгоритма по всем 4 тестовым паролям
    avg_time_by_algo = {}
    for algo_name in algorithms:
        times = [r["seconds_per_hash"] for r in rows if r["algorithm"] == algo_name]
        avg_time_by_algo[algo_name] = sum(times) / len(times)

    for algo_name, avg_t in avg_time_by_algo.items():
        est = theoretical_bruteforce_time(avg_t, 8)
        print(f"  {algo_name:<28} ~ {human_time(est)}")

    # сохраняем сырые данные в csv - пригодится для отчёта и для графика
    with open("hash_benchmark_results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["algorithm", "password_category", "password_length",
                                                "seconds_per_hash", "hashes_per_second"])
        writer.writeheader()
        writer.writerows(rows)

    print("\nСырые данные сохранены в hash_benchmark_results.csv")


if __name__ == "__main__":
    sys.exit(main())
