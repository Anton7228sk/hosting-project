import sqlite3
import os

# Имя файла базы данных
DB_NAME = "hosting.db"


def get_connection():
    """Создает соединение с базой данных."""
    conn = sqlite3.connect(DB_NAME)
    # Это чтобы получать результаты как словари (dict), а не цифры
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Создает таблицу, если её нет.
    Именно эта функция создает файл hosting.db!
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Создаем таблицу sites
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS sites (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT UNIQUE NOT NULL,
      container_id TEXT NOT NULL,
      domain TEXT NOT NULL
    )
  """
    )

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована (hosting.db)")


def add_site(name, container_id, domain):
    """Добавляет новый сайт в базу."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO sites (name, container_id, domain) VALUES (?, ?, ?)",
            (name, container_id, domain),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"⚠️ Сайт {name} уже есть в базе")
    finally:
        conn.close()


def get_all_sites():
    """Возвращает список всех сайтов."""
    conn = get_connection()
    sites = conn.execute("SELECT * FROM sites").fetchall()
    conn.close()
    return sites


def remove_site(name):
    """Удаляет сайт из базы по имени."""
    conn = get_connection()
    conn.execute("DELETE FROM sites WHERE name = ?", (name,))
    conn.commit()
    conn.close()
