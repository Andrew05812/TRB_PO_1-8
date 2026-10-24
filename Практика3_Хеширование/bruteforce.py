#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Практика 3. Переборщик паролей по хэшу.
Колесников А.Ю., БСБО-03-23, студ. билет 23Б0099

Что умеет:
  - SHA-1 и MD5 (быстрые алгоритмы, перебор идёт напрямую через hashlib);
  - bcrypt (cost берётся из самого хэша, ничего дополнительно указывать не надо);
  - Argon2id (параметры тоже берутся из строки хэша);
  - словарная атака (--dict) и атака по маске (--mask);
  - распараллеливание через ProcessPoolExecutor, потому что hashlib в CPython
    не отпускает GIL и потоки для перебора бесполезны;
  - режим --lab: прогон по 16 хэшам из методички и запись результатов в CSV;
  - --selftest: быстрая проверка, что реализация хэшей и масок вообще верная.

Примеры запуска:
  python bruteforce.py --hash 7c4a8d09ca3762af61e59520943dc26494f8941b --dict wordlist.txt
  python bruteforce.py --hash e10adc3949ba59abbe56e057f20f883e --mask "?d?d?d?d?d?d" --workers 4
  python bruteforce.py --lab --workers 4
  python bruteforce.py --selftest
"""

import argparse
import csv
import hashlib
import itertools
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

import bcrypt
from argon2.low_level import verify_secret, Type
from argon2.exceptions import VerifyMismatchError


# ---------------------------------------------------------------------------
# Хэши из методички. Лежат прямо в коде, чтобы --lab запускался одной командой
# и не зависел от того, открыт ли рядом PDF с заданием.
# ---------------------------------------------------------------------------
LAB_HASHES = [
    ("sha1", "лёгкий", "7c4a8d09ca3762af61e59520943dc26494f8941b"),
    ("sha1", "средний", "d0be2dc421be4fcd0172e5afceea3970e2f3d940"),
    ("sha1", "сложный", "666846867fc5e0a46a7afc53eb8060967862f333"),
    ("sha1", "очень сложный", "6e157c5da4410b7e9de85f5c93026b9176e69064"),
    ("md5", "лёгкий", "e10adc3949ba59abbe56e057f20f883e"),
    ("md5", "средний", "1f3870be274f6c49b3e31a0c6728957f"),
    ("md5", "сложный", "77892341aa9dc66e97f5c248782b5d92"),
    ("md5", "очень сложный", "686e697538050e4664636337cc3b834f"),
    ("bcrypt", "лёгкий", "$2a$10$z4u9ZkvopUiiytaNX7wfGedy9Lu2ywUxwYpbsAR5YBrAuUs3YGXdi"),
    ("bcrypt", "средний", "$2a$10$26GB/T2/6aTsMkTjCgqm/.JP8SUjr32Bhfn9m9smtDiIwM4QIt2ze"),
    ("bcrypt", "сложный", "$2a$10$Q9M0vLLrE4/nu/9JEMXFTewB3Yr9uMdIEZ1Sgdk1NQTjHwLN0asfi"),
    ("bcrypt", "очень сложный", "$2a$10$yZBadi8Szw0nItV2g96P6eqctI2kbG/.mb0uD/ID9tlof0zpJLLL2"),
    ("argon2", "лёгкий", "$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHQ$PUF5UxxoUY++mMekkQwFurL0ZsTtB7lelO23zcyZQ0c"),
    ("argon2", "средний", "$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHQ$HYQwRUw9VcfkvqkUQ5ppyYPom6f/ro3ZCXYznhrYZw4"),
    ("argon2", "сложный", "$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHQ$9asGA7Xv3vQBz7Yyh4/Ntw0GQgOg8R6OWolOfRETrEg"),
    ("argon2", "очень сложный", "$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHQ$+smq45/czydGj0lYNdZVXF++FOXJwrkXt6VUIcEauvo"),
]

# Человеческие названия для вывода и CSV
ALGO_TITLES = {
    "sha1": "SHA-1",
    "md5": "MD5",
    "bcrypt": "bcrypt",
    "argon2": "Argon2id",
}


# ---------------------------------------------------------------------------
# Разбор хэша и проверка одного кандидата
# ---------------------------------------------------------------------------

def detect_algorithm(target: str) -> str:
    """Определяем алгоритм по формату строки, чтобы не заставлять пользователя
    каждый раз писать --type. Префиксы у bcrypt и Argon2 однозначные, а SHA-1
    и MD5 различаются длиной (40 и 32 hex-символа)."""
    target = target.strip()
    if target.startswith("$argon2"):
        return "argon2"
    if target.startswith(("$2a$", "$2b$", "$2y$")):
        return "bcrypt"
    if re.fullmatch(r"[0-9a-fA-F]{40}", target):
        return "sha1"
    if re.fullmatch(r"[0-9a-fA-F]{32}", target):
        return "md5"
    raise ValueError("Не удалось определить алгоритм по хэшу, укажите --type вручную")


def validate_target(algorithm: str, target: str) -> None:
    """Проверяем хэш до запуска перебора. Иначе при опечатке в хэше программа
    молча переберёт весь словарь и скажет «не найден», хотя проблема в входных
    данных, а не в пароле."""
    target = target.strip()

    if algorithm in ("sha1", "md5"):
        need = 40 if algorithm == "sha1" else 32
        if len(target) != need or not re.fullmatch(r"[0-9a-fA-F]+", target):
            raise ValueError(f"Для {ALGO_TITLES[algorithm]} нужен {need}-символьный hex-хэш")

    elif algorithm == "bcrypt":
        try:
            bcrypt.checkpw(b"proverka", target.encode("ascii"))
        except ValueError as exc:
            raise ValueError("Строка не похожа на корректный bcrypt-хэш") from exc

    elif algorithm == "argon2":
        try:
            verify_secret(target.encode("ascii"), b"proverka", Type.ID)
        except VerifyMismatchError:
            pass  # хэш корректный, просто пароль не подошёл — это нормально
        except Exception as exc:
            raise ValueError("Строка не похожа на корректный Argon2id-хэш") from exc

    else:
        raise ValueError(f"Неизвестный алгоритм: {algorithm}")


def check_one(candidate: str, algorithm: str, target: str):
    """Проверка одного пароля. Возвращает сам пароль, если он подошёл, иначе None.
    Вынесена отдельно, потому что её же вызывает и последовательная
    самопроверка, и рабочий процесс пула."""
    data = candidate.encode("utf-8")

    if algorithm == "sha1":
        # Сравниваем сразу байты digest, а не hex-строки: так на каждый
        # кандидат не тратится время на перевод в hex и обратно.
        if hashlib.sha1(data).digest() == bytes.fromhex(target):
            return candidate
        return None

    if algorithm == "md5":
        if hashlib.md5(data).digest() == bytes.fromhex(target):
            return candidate
        return None

    if algorithm == "bcrypt":
        try:
            if bcrypt.checkpw(data, target.encode("ascii")):
                return candidate
        except ValueError:
            # bcrypt в новых версиях ругается на пароль длиннее 72 байт.
            # В словаре такого быть не должно, но пусть лучше пропустит,
            # чем уронит весь рабочий процесс.
            return None
        return None

    # Argon2id
    try:
        if verify_secret(target.encode("ascii"), data, Type.ID):
            return candidate
    except VerifyMismatchError:
        return None
    return None


def _check_batch(algorithm: str, target: str, batch: list):
    """Точка входа для дочернего процесса. Принимает пачку кандидатов и
    возвращает (пароль, позиция внутри пачки) либо None. Позиция нужна,
    чтобы в отчёте указать, на каком месте перебора пароль нашёлся,
    а не просто «где-то в этой пачке». Пачками работаем не просто так:
    гонять процесс на каждый пароль слишком дорого, особенно на Windows,
    где дочерний процесс запускается заново (spawn), а не через fork."""
    for index, candidate in enumerate(batch):
        if check_one(candidate, algorithm, target):
            return candidate, index
    return None


# ---------------------------------------------------------------------------
# Генераторы кандидатов
# ---------------------------------------------------------------------------

def iter_dictionary(path: str) -> Iterator[str]:
    """Читаем словарь построчно. Пустые строки и комментарии с # пропускаем,
    чтобы в wordlist.txt можно было делать пометки."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            word = line.rstrip("\r\n")
            if not word or word.startswith("#"):
                continue
            yield word


# Наборы символов для маски. Синтаксис как у hashcat: ?l ?u ?d ?s ?a,
# а ?? означает сам символ вопроса.
MASK_SETS = {
    "l": "abcdefghijklmnopqrstuvwxyz",
    "u": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "d": "0123456789",
    "s": "!@#$%^&*()-_=+[]{};:,.<>?/|~",
}
MASK_SETS["a"] = MASK_SETS["l"] + MASK_SETS["u"] + MASK_SETS["d"] + MASK_SETS["s"]


def parse_mask(mask: str) -> list:
    """Превращаем маску в список наборов символов по позициям.
    Например, "?d?d?l" -> [digits, digits, lowercase]."""
    positions = []
    i = 0
    while i < len(mask):
        ch = mask[i]
        if ch != "?":
            positions.append((ch,))
            i += 1
            continue

        if i + 1 >= len(mask):
            raise ValueError("Маска не может заканчиваться одним символом '?'")
        code = mask[i + 1]
        if code == "?":
            positions.append(("?",))
        elif code in MASK_SETS:
            positions.append(tuple(MASK_SETS[code]))
        else:
            raise ValueError(f"Неизвестный код маски: ?{code}")
        i += 2
    return positions


def iter_mask(mask: str) -> Iterator[str]:
    """Полный перебор по маске через декартово произведение наборов.
    itertools.product не строит весь список в памяти, поэтому маска
    ?a?a?a?a?a?a (около 7 млрд вариантов) не упадёт по памяти сразу."""
    positions = parse_mask(mask)
    for combo in itertools.product(*positions):
        yield "".join(combo)


# ---------------------------------------------------------------------------
# Сам перебор
# ---------------------------------------------------------------------------

@dataclass
class CrackResult:
    found: Optional[str]
    elapsed: float
    tried: int
    reason: str  # found / not_found / timeout / no_candidates
    found_position: int = 0  # 1-based место пароля в потоке кандидатов

    @property
    def rate(self) -> float:
        return self.tried / self.elapsed if self.elapsed > 0 else 0.0


def default_chunk_size(algorithm: str) -> int:
    """Размер пачки зависит от стоимости одного хэша. Для SHA-1/MD5 пачка
    большая, чтобы не тратить время на передачу задач между процессами.
    Для bcrypt/Argon2 наоборот: один хэш считается десятки миллисекунд,
    большая пачка означала бы, что после находки процессы ещё долго
    досчитывают уже ненужные варианты."""
    if algorithm in ("sha1", "md5"):
        return 50_000
    if algorithm == "bcrypt":
        return 16
    return 8  # Argon2: 64 МБ на хэш, лишнюю память тоже не хочется занимать


def default_workers(algorithm: str) -> int:
    """Для Argon2 ограничиваем число процессов: каждый ест 64 МБ, и на
    машине с 16 ядрами 16 процессов съели бы целый гигабайт."""
    cpu = os.cpu_count() or 4
    if algorithm == "argon2":
        return max(1, min(cpu, 4))
    if algorithm == "bcrypt":
        return max(1, min(cpu, 8))
    return max(1, cpu)


def crack(candidates: Iterable[str], algorithm: str, target: str, workers: int,
          chunk_size: int, max_candidates: int = 0, timeout: float = 0,
          quiet: bool = False) -> CrackResult:
    """Основной цикл перебора.

    Идея: главный процесс режет поток кандидатов на пачки и держит в работе
    примерно 2 * workers пачек. Как только какая-то пачка вернула пароль,
    остальные отменяются. Так мы не ждём, пока отработает весь словарь,
    и при этом процессы не простаивают без работы.
    """
    started = time.perf_counter()
    tried = 0
    found = None
    found_position = 0
    reason = "not_found"
    last_report = started

    def batches():
        """Отдаём пачки вместе с их начальной позицией в общем потоке.
        Позиция нужна для точного отчёта: сколько кандидатов прошли,
        прежде чем нашли пароль."""
        buf = []
        produced = 0
        for candidate in candidates:
            if max_candidates and produced >= max_candidates:
                return
            buf.append(candidate)
            produced += 1
            if len(buf) >= chunk_size:
                yield produced - len(buf), buf
                buf = []
        if buf:
            yield produced - len(buf), buf

    batch_iter = batches()
    source_done = False
    pending = {}
    pool = ProcessPoolExecutor(max_workers=workers)

    try:
        def submit_next() -> None:
            nonlocal source_done
            try:
                start, batch = next(batch_iter)
            except StopIteration:
                source_done = True
                return
            pending[pool.submit(_check_batch, algorithm, target, batch)] = (start, len(batch))

        # Набираем очередь задач
        while len(pending) < workers * 2 and not source_done:
            submit_next()

        while pending:
            done, _ = wait(pending.keys(), timeout=0.25, return_when=FIRST_COMPLETED)
            now = time.perf_counter()

            for future in done:
                start, size = pending.pop(future)
                tried += size
                result = future.result()
                if result is not None and found is None:
                    candidate, offset = result
                    found = candidate
                    found_position = start + offset + 1

            if found is not None:
                reason = "found"
                break

            if timeout and now - started >= timeout:
                reason = "timeout"
                break

            while len(pending) < workers * 2 and not source_done:
                submit_next()

            # Раз в 5 секунд показываем, что программа жива. Для bcrypt на
            # большом словаре это важно: иначе кажется, что всё зависло.
            if not quiet and now - last_report >= 5:
                rate = tried / (now - started) if now > started else 0
                print(f"  ... проверено {tried:,} вариантов, {rate:,.0f}/с".replace(",", " "),
                      file=sys.stderr)
                last_report = now
    finally:
        elapsed = time.perf_counter() - started
        # wait=True нужен, чтобы корректно завершить дочерние процессы и не
        # оставить висящие задачи при выходе. Время атаки уже посчитано выше.
        pool.shutdown(wait=True, cancel_futures=True)

    if found is None and reason == "not_found" and tried == 0:
        reason = "no_candidates"

    return CrackResult(found, elapsed, tried, reason, found_position)


# ---------------------------------------------------------------------------
# Лабораторный прогон и CSV
# ---------------------------------------------------------------------------

def fmt_seconds(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f} мс"
    if seconds < 60:
        return f"{seconds:.2f} с"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f} мин"
    return f"{minutes / 60:.1f} ч"


def write_csv(path: str, rows: list, append: bool = False) -> None:
    fields = ["algorithm", "category", "attack", "hash", "password", "found",
              "found_position", "elapsed_seconds", "candidates_tried",
              "hashes_per_second", "workers"]
    # utf-8-sig, чтобы Excel не показывал русские категории кракозябрами
    mode = "a" if append and os.path.exists(path) else "w"
    with open(path, mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if mode == "w":
            writer.writeheader()
        writer.writerows(rows)


def make_row(algorithm: str, category: str, attack: str, target: str,
             result: CrackResult, workers: int) -> dict:
    return {
        "algorithm": ALGO_TITLES[algorithm],
        "category": category,
        "attack": attack,
        "hash": target,
        "password": result.found or "",
        "found": 1 if result.found else 0,
        "found_position": result.found_position,
        "elapsed_seconds": f"{result.elapsed:.4f}",
        "candidates_tried": result.tried,
        "hashes_per_second": f"{result.rate:.1f}",
        "workers": workers,
    }


def run_lab(wordlist: str, workers_override: int, results_path: str) -> int:
    """Полный прогон по заданию: словарь по всем 16 хэшам плюс отдельно
    показываем настоящий полный перебор по маске для SHA-1 и MD5."""
    if not os.path.isfile(wordlist):
        print(f"Не найден словарь: {wordlist}", file=sys.stderr)
        return 2

    rows = []
    found_count = 0
    total = 0
    lab_started = time.perf_counter()

    for algorithm, category, target in LAB_HASHES:
        total += 1
        workers = workers_override or default_workers(algorithm)
        chunk = default_chunk_size(algorithm)

        print(f"\n[{ALGO_TITLES[algorithm]} / {category}] {target}", flush=True)
        print(f"  словарная атака: {workers} проц., пачка {chunk}", flush=True)

        # Для словаря заново открываем файл: генератор одноразовый,
        # а нам нужен свежий проход на каждый хэш.
        result = crack(iter_dictionary(wordlist), algorithm, target,
                       workers=workers, chunk_size=chunk)
        rows.append(make_row(algorithm, category, "dict", target, result, workers))

        if result.found:
            found_count += 1
            print(f"  пароль: {result.found} (позиция в словаре: {result.found_position:,})".replace(",", " "))
        else:
            print("  пароль не найден в словаре")
        print(f"  время: {fmt_seconds(result.elapsed)}, проверено {result.tried:,}, "
              f"скорость {result.rate:,.0f} хэш/с".replace(",", " "), flush=True)

    # Отдельный настоящий перебор по маске. Берём лёгкие хэши SHA-1 и MD5:
    # там пароль из шести цифр, то есть ровно 1 000 000 вариантов — как раз
    # тот случай, где видно разницу между «словарём» и полным перебором.
    for algorithm, label in (("sha1", "SHA-1"), ("md5", "MD5")):
        target = next(h for a, c, h in LAB_HASHES if a == algorithm and c == "лёгкий")
        workers = workers_override or default_workers(algorithm)
        print(f"\n[{label} / лёгкий, полный перебор] маска ?d?d?d?d?d?d", flush=True)
        result = crack(iter_mask("?d?d?d?d?d?d"), algorithm, target,
                       workers=workers, chunk_size=default_chunk_size(algorithm),
                       max_candidates=1_000_000)
        rows.append(make_row(algorithm, "лёгкий", "mask ?d?d?d?d?d?d", target, result, workers))
        if result.found:
            print(f"  пароль: {result.found} (позиция в переборе: {result.found_position:,})".replace(",", " "))
        else:
            print("  пароль не найден")
        print(f"  время: {fmt_seconds(result.elapsed)}, проверено {result.tried:,}, "
              f"скорость {result.rate:,.0f} хэш/с".replace(",", " "), flush=True)

    write_csv(results_path, rows)
    lab_elapsed = time.perf_counter() - lab_started

    print("\n" + "=" * 70)
    print(f"Найдено словарём: {found_count} из {total} хэшей")
    print(f"Общее время прогона: {fmt_seconds(lab_elapsed)}")
    print(f"Результаты сохранены в {results_path}")
    print("=" * 70)
    return 0


# ---------------------------------------------------------------------------
# Самопроверка
# ---------------------------------------------------------------------------

def run_selftest() -> int:
    """Проверяем не «взлом», а собственную реализацию: эталонные значения
    SHA-1/MD5, разбор маски и по одному известному паролю для каждого
    поддерживаемого формата. Если тут всё зелёное, значит переборщик
    сравнивает хэши правильно."""
    print("Самопроверка переборщика")
    print("-" * 50)

    assert hashlib.sha1(b"abc").hexdigest() == "a9993e364706816aba3e25717850c26c9cd0d89d"
    assert hashlib.md5(b"abc").hexdigest() == "900150983cd24fb0d6963f7d28e17f72"
    print("OK  эталонные SHA-1 и MD5 для строки 'abc'")

    mask_values = list(iter_mask("?d?d"))
    assert len(mask_values) == 100 and mask_values[0] == "00" and mask_values[-1] == "99"
    assert list(iter_mask("a?d??")) == ["a0?", "a1?", "a2?", "a3?", "a4?",
                                        "a5?", "a6?", "a7?", "a8?", "a9?"]
    print("OK  разбор маски (100 вариантов ?d?d, ?? как literal)")

    # check_one напрямую, без пула процессов
    assert check_one("abc", "sha1", hashlib.sha1(b"abc").hexdigest()) == "abc"
    assert check_one("abc", "md5", hashlib.md5(b"abc").hexdigest()) == "abc"
    print("OK  проверка одного кандидата для SHA-1 и MD5")

    target_sha1 = hashlib.sha1(b"Create").hexdigest()
    result = crack(["123456", "apple", "Create"], "sha1", target_sha1,
                   workers=2, chunk_size=1, quiet=True)
    assert result.found == "Create", result
    print("OK  словарный перебор с двумя процессами")

    # bcrypt и Argon2 проверяем на заведомо известных хэшах из методички
    bcrypt_hash = next(h for a, c, h in LAB_HASHES if a == "bcrypt" and c == "лёгкий")
    assert check_one("123456", "bcrypt", bcrypt_hash) == "123456"
    print("OK  bcrypt: пароль 123456 подошёл к эталонному хэшу")

    argon_hash = next(h for a, c, h in LAB_HASHES if a == "argon2" and c == "лёгкий")
    assert check_one("123456", "argon2", argon_hash) == "123456"
    print("OK  Argon2id: пароль 123456 подошёл к эталонному хэшу")

    print("-" * 50)
    print("Все проверки пройдены")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Переборщик паролей по хэшу (SHA-1, MD5, bcrypt, Argon2id)")
    parser.add_argument("--hash", help="хэш, который нужно подобрать")
    parser.add_argument("--type", choices=["auto", "sha1", "md5", "bcrypt", "argon2"],
                        default="auto", help="алгоритм (по умолчанию определяется сам)")
    parser.add_argument("--dict", help="файл словаря, по одному паролю в строке")
    parser.add_argument("--mask", help="маска, например ?d?d?d?d или ?l?l?d?d")
    parser.add_argument("--workers", type=int, default=0,
                        help="число процессов (0 — подобрать автоматически)")
    parser.add_argument("--chunk-size", type=int, default=0,
                        help="сколько кандидатов отдавать процессу за раз (0 — авто)")
    parser.add_argument("--max-candidates", type=int, default=0,
                        help="остановиться после N кандидатов (0 — без ограничения)")
    parser.add_argument("--timeout", type=float, default=0,
                        help="остановиться через N секунд (0 — без ограничения)")
    parser.add_argument("--lab", action="store_true",
                        help="прогон по всем хэшам из методички")
    parser.add_argument("--selftest", action="store_true",
                        help="быстрая проверка реализации")
    parser.add_argument("--wordlist", default="wordlist.txt",
                        help="словарь для режима --lab (по умолчанию wordlist.txt)")
    parser.add_argument("--results", default="crack_results.csv",
                        help="куда сохранить CSV в режиме --lab")
    parser.add_argument("--csv", help="дописать результат одиночного запуска в CSV")
    parser.add_argument("--quiet", action="store_true", help="не печатать прогресс")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.selftest:
        return run_selftest()

    if args.lab:
        return run_lab(args.wordlist, args.workers, args.results)

    if not args.hash:
        print("Нужен --hash, либо --lab, либо --selftest", file=sys.stderr)
        return 2
    if not args.dict and not args.mask:
        print("Нужна хотя бы одна атака: --dict и/или --mask", file=sys.stderr)
        return 2

    target = args.hash.strip()
    algorithm = detect_algorithm(target) if args.type == "auto" else args.type
    try:
        validate_target(algorithm, target)
    except ValueError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    workers = args.workers or default_workers(algorithm)
    chunk = args.chunk_size or default_chunk_size(algorithm)

    def candidates() -> Iterator[str]:
        # Сначала словарь, потом маска. Так можно одной командой проверить
        # сначала типовые пароли, а потом добить перебором по шаблону.
        if args.dict:
            yield from iter_dictionary(args.dict)
        if args.mask:
            yield from iter_mask(args.mask)

    attack = []
    if args.dict:
        attack.append("dict")
    if args.mask:
        attack.append(f"mask {args.mask}")

    print(f"Алгоритм: {ALGO_TITLES[algorithm]}")
    print(f"Процессов: {workers}, пачка: {chunk}")
    print(f"Атака: {', '.join(attack)}")
    if args.max_candidates:
        print(f"Лимит кандидатов: {args.max_candidates:,}".replace(",", " "))
    if args.timeout:
        print(f"Лимит времени: {args.timeout} с")

    result = crack(candidates(), algorithm, target, workers=workers, chunk_size=chunk,
                   max_candidates=args.max_candidates, timeout=args.timeout,
                   quiet=args.quiet)

    print("-" * 50)
    if result.found:
        print(f"Пароль найден: {result.found}")
        print(f"Позиция в переборе: {result.found_position:,}".replace(",", " "))
    elif result.reason == "timeout":
        print("Пароль не найден: истёк лимит времени")
    else:
        print("Пароль не найден: кандидаты закончились")
    print(f"Время: {fmt_seconds(result.elapsed)}")
    print(f"Проверено вариантов: {result.tried:,}".replace(",", " "))
    print(f"Скорость: {result.rate:,.0f} хэш/с".replace(",", " "))

    if args.csv:
        row = make_row(algorithm, "—", ", ".join(attack), target, result, workers)
        write_csv(args.csv, [row], append=True)
        print(f"Результат дописан в {args.csv}")

    return 0 if result.found else 1


if __name__ == "__main__":
    sys.exit(main())
