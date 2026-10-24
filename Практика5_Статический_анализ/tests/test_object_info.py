#!/usr/bin/env python3
# Проверки защищённой страницы object_info.php.
# Запускать при поднятом SecureObjectInfo:
#   python tests/test_object_info.py
# Внешних целей нет, только 127.0.0.1.

import os
import re
import sys

import requests

BASE = os.environ.get("P5_BASE", "http://127.0.0.1:8082/object_info.php")
LOGIN = "testuser"
PASSWORD = "Summer2024!"


def get_token(session):
    response = session.get(BASE)
    match = re.search(r'name="user_token" value="([0-9a-f]+)"', response.text)
    if not match:
        raise AssertionError("CSRF-токен не найден на странице")
    return match.group(1)


def main():
    checks = []

    # 1. Обычный вход и вывод объекта.
    session = requests.Session()
    token = get_token(session)
    response = session.get(
        BASE,
        params={"username": LOGIN, "password": PASSWORD, "user_token": token,
                "Login": "Login", "id": 2},
        allow_redirects=False,
    )
    checks.append(("вход с верными данными", response.status_code == 302,
                   response.headers.get("Location", "")))

    response = session.get(BASE, params={"id": 2})
    checks.append(("объект 2 отображается",
                   "Счёт за сентябрь" in response.text and "petrov" in response.text,
                   str(response.status_code)))

    # 2. SQL-инъекция в логине.
    session2 = requests.Session()
    token2 = get_token(session2)
    response = session2.get(
        BASE,
        params={"username": "' OR '1'='1", "password": "x", "user_token": token2,
                "Login": "Login", "id": 1},
    )
    checks.append(("инъекция в логине отклонена",
                   "incorrect" in response.text and "Договор" not in response.text,
                   str(response.status_code)))

    # 3. SQL-инъекция в id после входа.
    response = session.get(BASE, params={"id": "2' OR '1'='1"})
    checks.append(("инъекция в id не выводит чужие объекты",
                   "Договор поставки" in response.text
                   and "Счёт за сентябрь" not in response.text
                   and "Акт приёмки" not in response.text,
                   str(response.status_code)))

    # 4. Запрос без CSRF-токена.
    session3 = requests.Session()
    session3.get(BASE)
    response = session3.get(
        BASE,
        params={"username": LOGIN, "password": PASSWORD, "Login": "Login", "id": 1},
    )
    checks.append(("без CSRF-токена вход запрещён",
                   "Сессия устарела" in response.text, str(response.status_code)))

    failed = 0
    for name, ok, detail in checks:
        print(("OK   " if ok else "FAIL ") + name + " (" + detail + ")")
        failed += 0 if ok else 1

    print("ИТОГ:", "все проверки пройдены" if failed == 0 else f"ошибок {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
