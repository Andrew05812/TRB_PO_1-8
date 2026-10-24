import os
import time

import psycopg2
from flask import Flask, render_template

app = Flask(__name__)
DATABASE_URL = os.environ["DATABASE_URL"]


def connect():
    # Небольшой retry: контейнер приложения может стартовать чуть раньше
    # Postgres, хотя depends_on с healthcheck это в основном закрывает.
    last_error = None
    for _ in range(30):
        try:
            return psycopg2.connect(DATABASE_URL)
        except psycopg2.OperationalError as exc:
            last_error = exc
            time.sleep(1)
    raise last_error


def init_db():
    with connect() as conn:
        with conn.cursor() as cur:
            # Два gunicorn-воркера стартуют одновременно и оба вызывают
            # init_db(). Без блокировки они могли бы оба увидеть COUNT(*)=0
            # и вставить стартовые строки дважды.
            cur.execute("SELECT pg_advisory_xact_lock(20261024)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS objects (
                    id         SERIAL PRIMARY KEY,
                    name       TEXT NOT NULL,
                    owner      TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("SELECT COUNT(*) FROM objects")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    "INSERT INTO objects (name, owner) VALUES (%s, %s)",
                    [
                        ("Договор поставки", "ivanov"),
                        ("Счёт за сентябрь", "petrov"),
                        ("Акт приёмки", "sidorov"),
                    ],
                )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS visits (
                    id         SERIAL PRIMARY KEY,
                    visited_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )


@app.get("/")
def index():
    with connect() as conn:
        with conn.cursor() as cur:
            # Обычный параметризованный запрос: пользовательских данных в SQL
            # здесь нет, но правило всё равно соблюдается.
            cur.execute("INSERT INTO visits DEFAULT VALUES")
            cur.execute("SELECT id, name, owner, created_at FROM objects ORDER BY id")
            objects = cur.fetchall()
            cur.execute("SELECT COUNT(*) FROM visits")
            visits = cur.fetchone()[0]
    return render_template("index.html", objects=objects, visits=visits)


@app.get("/healthz")
def healthz():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    return "ok\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


# Под gunicorn __main__ не выполняется, поэтому схему создаём при импорте.
# Функция идемпотентна: CREATE IF NOT EXISTS и проверка COUNT(*) = 0.
init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
