import sqlite3
import os

# === ВИПРАВЛЕННЯ ШЛЯХУ ===
# Встановлюємо шлях до бази даних в окремій папці (не в user_data)
DB_PATH = '/app/database' 
DB_NAME = os.path.join(DB_PATH, "hosting.db")
# =========================


def get_connection():
    """Создает соединение с базой данных."""
    # Используем полный путь к файлу базы данных (DB_NAME)
    conn = sqlite3.connect(DB_NAME)
    # Это чтобы получать результаты как словари (dict), а не цифры
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Создает таблицы, если их нет.
    Именно эта функция создает файл hosting.db!
    """
    # Гарантируем, что папка существует перед попыткой создания базы данных.
    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH)
        
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Таблица users (клиенты)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            plan TEXT DEFAULT 'free',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # 2. Таблица sites (сайты)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            container_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            user_id INTEGER,
            site_type TEXT DEFAULT 'static',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # 3. Таблица resource_limits (обмеження ресурсів)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS resource_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER UNIQUE NOT NULL,
            cpu_limit INTEGER DEFAULT 50,
            ram_limit_mb INTEGER DEFAULT 512,
            disk_limit_mb INTEGER DEFAULT 1024,
            bandwidth_limit_mb INTEGER DEFAULT 10240,
            FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE
        )
        """
    )

    # 4. Таблица backups (резервні копії)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            backup_path TEXT NOT NULL,
            size_mb REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE
        )
        """
    )

    # 5. Таблица site_types (типи хостингу)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS site_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            docker_image TEXT NOT NULL
        )
        """
    )

    # Додаємо типи хостингу за замовчуванням
    site_types_data = [
        ('static', 'Static HTML/CSS/JS hosting', 'nginx:alpine'),
        ('php', 'PHP hosting with Apache', 'php:8.2-apache'),
        ('python', 'Python Flask/Django hosting', 'python:3.11-slim'),
        ('nodejs', 'Node.js hosting', 'node:20-alpine')
    ]
    
    for site_type in site_types_data:
        cursor.execute(
            "INSERT OR IGNORE INTO site_types (name, description, docker_image) VALUES (?, ?, ?)",
            site_type
        )

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована (hosting.db) с расширенной схемой")


def add_site(name, container_id, domain, user_id=None, site_type='static'):
    """Добавляет новый сайт в базу."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO sites (name, container_id, domain, user_id, site_type) VALUES (?, ?, ?, ?, ?)",
            (name, container_id, domain, user_id, site_type),
        )
        conn.commit()
        site_id = cursor.lastrowid
        
        # Автоматически создаем стандартные лимиты для нового сайта
        set_resource_limits(site_id)
        
        return site_id
    except sqlite3.IntegrityError:
        print(f"⚠️ Сайт {name} уже есть в базе")
        return None
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


# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С USERS ==========

def create_user(email, password_hash, name=None, plan='free'):
    """Создает нового пользователя."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, name, plan) VALUES (?, ?, ?, ?)",
            (email, password_hash, name, plan)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        print(f"⚠️ Пользователь с email {email} уже существует")
        return None
    finally:
        conn.close()


def get_user(user_id=None, email=None):
    """Получает пользователя по ID или email."""
    conn = get_connection()
    if user_id:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    elif email:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    else:
        user = None
    conn.close()
    return user


def get_all_users():
    """Возвращает список всех пользователей."""
    conn = get_connection()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return users


def update_user(user_id, **kwargs):
    """Обновляет данные пользователя."""
    conn = get_connection()
    allowed_fields = ['email', 'name', 'plan', 'status']
    updates = []
    values = []
    
    for field, value in kwargs.items():
        if field in allowed_fields:
            updates.append(f"{field} = ?")
            values.append(value)
    
    if updates:
        values.append(user_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        conn.execute(query, values)
        conn.commit()
    conn.close()


def delete_user(user_id):
    """Удаляет пользователя."""
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С RESOURCE LIMITS ==========

def set_resource_limits(site_id, cpu_limit=50, ram_limit_mb=512, disk_limit_mb=1024, bandwidth_limit_mb=10240):
    """Устанавливает ограничения ресурсов для сайта."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO resource_limits (site_id, cpu_limit, ram_limit_mb, disk_limit_mb, bandwidth_limit_mb)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(site_id) DO UPDATE SET
                cpu_limit = excluded.cpu_limit,
                ram_limit_mb = excluded.ram_limit_mb,
                disk_limit_mb = excluded.disk_limit_mb,
                bandwidth_limit_mb = excluded.bandwidth_limit_mb
            """,
            (site_id, cpu_limit, ram_limit_mb, disk_limit_mb, bandwidth_limit_mb)
        )
        conn.commit()
    finally:
        conn.close()


def get_resource_limits(site_id):
    """Получает ограничения ресурсов для сайта."""
    conn = get_connection()
    limits = conn.execute("SELECT * FROM resource_limits WHERE site_id = ?", (site_id,)).fetchone()
    conn.close()
    return limits


# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С BACKUPS ==========

def create_backup(site_id, backup_path, size_mb=0):
    """Создает запись о резервной копии."""
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO backups (site_id, backup_path, size_mb) VALUES (?, ?, ?)",
        (site_id, backup_path, size_mb)
    )
    conn.commit()
    backup_id = cursor.lastrowid
    conn.close()
    return backup_id


def list_backups(site_id=None):
    """Возвращает список резервных копий."""
    conn = get_connection()
    if site_id:
        backups = conn.execute("SELECT * FROM backups WHERE site_id = ? ORDER BY created_at DESC", (site_id,)).fetchall()
    else:
        backups = conn.execute("SELECT * FROM backups ORDER BY created_at DESC").fetchall()
    conn.close()
    return backups


def delete_backup(backup_id):
    """Удаляет запись о резервной копии."""
    conn = get_connection()
    conn.execute("DELETE FROM backups WHERE id = ?", (backup_id,))
    conn.commit()
    conn.close()


# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С SITE TYPES ==========

def get_site_types():
    """Возвращает все доступные типы хостинга."""
    conn = get_connection()
    types = conn.execute("SELECT * FROM site_types").fetchall()
    conn.close()
    return types


def get_site_type(name):
    """Получает информацию о типе хостинга."""
    conn = get_connection()
    site_type = conn.execute("SELECT * FROM site_types WHERE name = ?", (name,)).fetchone()
    conn.close()
    return site_type