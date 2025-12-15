import os
import shutil
import zipfile  # <--- НОВАЯ БИБЛИОТЕКА
from flask import Flask, render_template, request, redirect, url_for

# Импортируем модули
from core_engine import docker_manager
from web_panel import database

app = Flask(__name__)

# Папка для данных
USER_DATA_DIR = os.path.abspath("user_data")

# Инициализация
if not os.path.exists(USER_DATA_DIR):
    os.makedirs(USER_DATA_DIR)
database.init_db()


def restore_containers():
    """Восстанавливает контейнеры, которые были активны до перезагрузки."""
    sites = database.get_all_sites()
    print(f"🔄 Попытка восстановить {len(sites)} контейнеров...")
    for site in sites:
        try:
            # Используем новую функцию is_container_running
            if not docker_manager.is_container_running(site["name"]):
                docker_manager.start_container(site["name"])
                print(f"✅ Восстановлен: {site['name']}")
            else:
                print(f"⏩ Контейнер {site['name']} уже запущен.")
        except Exception as e:
            # Это может произойти, если папка с данными была удалена вручную
            print(f"❌ Ошибка при восстановлении {site['name']}: {e}")


# Вызов функции при старте приложения
restore_containers()
# --- КОНЕЦ ВОССТАНОВЛЕНИЯ ---


@app.route("/")
def index():
    sites = database.get_all_sites()
    return render_template("index.html", sites=sites)


@app.route("/create", methods=["POST"])
def create():
    site_name = request.form.get("site_name").strip().lower()

    # Получаем файл из формы
    uploaded_file = request.files.get("html_file")

    # 1. Валидация имени
    if not site_name.isalnum():
        return "Ошибка: Имя только буквы и цифры!", 400

    # 2. Создаем папку сайта
    site_path = os.path.join(USER_DATA_DIR, site_name)
    if os.path.exists(site_path):
        return "Ошибка: Сайт уже существует!", 400
    os.makedirs(site_path)

    # --- ЛОГИКА ЗАГРУЗКИ ФАЙЛОВ (НОВАЯ) ---

    # Вариант А: Пользователь загрузил ZIP-архив
    if uploaded_file and uploaded_file.filename.endswith(".zip"):
        # Сохраняем архив временно
        zip_path = os.path.join(site_path, "upload.zip")
        uploaded_file.save(zip_path)

        try:
            # Распаковываем
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(site_path)

            # Удаляем сам архив, чтобы не занимал место
            os.remove(zip_path)
        except Exception as e:
            return f"Ошибка распаковки архива: {e}", 500

    # Вариант Б: Пользователь ничего не загрузил (создаем заглушку)
    else:
        with open(os.path.join(site_path, "index.html"), "w") as f:
            f.write(f"<h1>Site: {site_name}</h1><p>Waiting for content...</p>")

    # --- КОНЕЦ ЛОГИКИ ЗАГРУЗКИ ---

    # 3. Запускаем контейнер
    try:
        container = docker_manager.start_container(site_name)
        if container:
            domain = f"{site_name}.localhost"
            database.add_site(site_name, container.short_id, domain)
        else:
            return "Ошибка Docker", 500

    except Exception as e:
        return f"Критическая ошибка: {e}", 500

    return redirect(url_for("index"))


@app.route("/delete/<site_name>", methods=["POST"])
def delete(site_name):
    docker_manager.stop_container(site_name)
    database.remove_site(site_name)
    shutil.rmtree(os.path.join(USER_DATA_DIR, site_name), ignore_errors=True)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
