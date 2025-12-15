import os
import shutil
import zipfile  # <--- НОВАЯ БИБЛИОТЕКА
from flask import Flask, render_template, request, redirect, url_for
import docker

# Импортируем модули
from core_engine import docker_manager
from core_engine import metrics as metrics_module
from web_panel import database

app = Flask(__name__)

# Папка для данных
USER_DATA_DIR = "/app/user_data"

# Инициализация
if not os.path.exists(USER_DATA_DIR):
    os.makedirs(USER_DATA_DIR)
database.init_db()


def autostart_sites():
    """Автоматично запускає всі сайти з бази при старті панелі"""
    print("\n🔄 Автозапуск контейнерів сайтів...")
    sites = database.get_all_sites()
    
    for site in sites:
        try:
            # Перевіряємо чи контейнер існує
            docker_client = docker.from_env()
            try:
                container = docker_client.containers.get(site['name'])
                if container.status != 'running':
                    container.start()
                    print(f"  ✅ Запущено: {site['name']}")
                else:
                    print(f"  ✓ Вже працює: {site['name']}")
            except docker.errors.NotFound:
                # Контейнера немає - створюємо новий
                print(f"  🆕 Створюю контейнер: {site['name']}")
                container = docker_manager.start_container(site['name'])
                if container:
                    # Оновлюємо container_id
                    conn = database.get_connection()
                    conn.execute('UPDATE sites SET container_id = ? WHERE name = ?', 
                               (container.short_id, site['name']))
                    conn.commit()
                    conn.close()
                    print(f"  ✅ Створено: {site['name']}")
        except Exception as e:
            print(f"  ❌ Помилка для {site['name']}: {e}")
    
    print("✅ Автозапуск завершено\n")


# Запускаємо автостарт при завантаженні
autostart_sites()


def autostart_sites():
    """Автоматично запускає всі сайти з бази при старті панелі"""
    print("🔄 Перевіряю контейнери сайтів...")
    docker_client = docker.from_env()
    sites = database.get_all_sites()
    
    # Спочатку підключаємо Traefik до всіх ізольованих мереж
    try:
        traefik = docker_client.containers.get("traefik_proxy")
        for site in sites:
            network_name = f"{site['name']}_isolated"
            try:
                network = docker_client.networks.get(network_name)
                networks = traefik.attrs['NetworkSettings']['Networks']
                if network_name not in networks:
                    network.connect(traefik)
                    print(f"🔗 Traefik підключено до {network_name}")
            except docker.errors.NotFound:
                pass  # Мережа не існує, буде створена пізніше
            except docker.errors.APIError:
                pass  # Вже підключено
    except Exception as e:
        print(f"⚠️  Не вдалося підключити Traefik: {e}")
    
    for site in sites:
        site_name = site['name']
        site_id = site['id']
        
        # Отримуємо ліміти з бази
        limits = database.get_resource_limits(site_id)
        cpu_limit = limits['cpu_limit'] if limits else 50
        ram_limit = limits['ram_limit_mb'] if limits else 512
        
        try:
            # Перевіряємо чи контейнер існує
            container = docker_client.containers.get(site_name)
            if container.status != 'running':
                print(f"▶️  Запускаю зупинений контейнер {site_name}...")
                container.start()
            else:
                print(f"✅ Контейнер {site_name} вже працює")
        except docker.errors.NotFound:
            # Контейнер не існує - створюємо новий з лімітами
            print(f"🆕 Створюю новий контейнер для {site_name} (CPU: {cpu_limit}%, RAM: {ram_limit}MB)...")
            container = docker_manager.start_container(site_name, cpu_limit=cpu_limit, ram_limit_mb=ram_limit)
            if container:
                # Оновлюємо container_id в базі
                conn = database.get_connection()
                conn.execute('UPDATE sites SET container_id = ? WHERE name = ?', 
                           (container.short_id, site_name))
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"❌ Помилка запуску {site_name}: {e}")

# Автозапуск сайтів при старті
autostart_sites()


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

    # 3. Запускаем контейнер з лімітами (дефолтні: 50% CPU, 512MB RAM)
    try:
        container = docker_manager.start_container(site_name, cpu_limit=50, ram_limit_mb=512)
        if container:
            domain = f"{site_name}.localhost"
            site_id = database.add_site(site_name, container.short_id, domain)
            # Додаємо ліміти в базу
            database.set_resource_limits(site_id, cpu_limit=50, ram_limit_mb=512, disk_limit_mb=1024)
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


@app.route("/database")
def view_database():
    """Сторінка детальної інформації про сайти"""
    docker_client = docker.from_env()
    sites = database.get_all_sites()
    
    # Збираємо детальну інформацію про кожен сайт
    sites_info = []
    for site in sites:
        site_name = site['name']
        site_path = os.path.join(USER_DATA_DIR, site_name)
        
        # Отримуємо інформацію про контейнер
        container_info = {
            'id': 'N/A',
            'status': 'Не запущено',
            'ip': 'N/A'
        }
        try:
            container = docker_client.containers.get(site_name)
            container_info = {
                'id': container.short_id,
                'status': container.status,
                'ip': container.attrs['NetworkSettings']['Networks'].get('hosting-project_default', {}).get('IPAddress', 'N/A')
            }
        except:
            pass
        
        # Аналізуємо типи файлів
        file_types = {}
        total_size = 0
        file_count = 0
        
        if os.path.exists(site_path):
            for root, dirs, files in os.walk(site_path):
                for file in files:
                    file_count += 1
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        total_size += file_size
                        ext = os.path.splitext(file)[1].lower() or 'без розширення'
                        file_types[ext] = file_types.get(ext, 0) + 1
                    except:
                        pass
        
        # Топ-5 типів файлів
        top_types = sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:5]
        
        sites_info.append({
            'name': site_name,
            'domain': f"{site_name}.localhost",
            'created_at': site['created_at'] if 'created_at' in site.keys() else 'N/A',
            'owner': site['user_id'] if site['user_id'] else 'Система',
            'container': container_info,
            'file_stats': {
                'count': file_count,
                'size_mb': round(total_size / (1024*1024), 2),
                'types': top_types
            }
        })
    
    return render_template("database.html", sites_info=sites_info)


@app.route("/metrics")
def view_metrics():
    """Сторінка моніторингу метрик"""
    sites_metrics = metrics_module.get_all_sites_metrics()
    return render_template("metrics.html", sites_metrics=sites_metrics)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
