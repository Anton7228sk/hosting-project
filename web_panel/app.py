import os
import shutil
import zipfile
from flask import Flask, render_template, request, redirect, url_for
import docker

from core_engine import docker_manager
from core_engine import metrics as metrics_module
from web_panel import database

app = Flask(__name__)

USER_DATA_DIR = "/app/user_data"

if not os.path.exists(USER_DATA_DIR):
    os.makedirs(USER_DATA_DIR)
database.init_db()


def autostart_sites():
    """Automatycznie uruchamia wszystkie strony z bazy przy starcie panelu"""
    print("🔄 Sprawdzam kontenery stron...")
    docker_client = docker.from_env()
    sites = database.get_all_sites()
    
    # Najpierw łączymy Traefik ze wszystkimi izolowanymi sieciami
    try:
        traefik = docker_client.containers.get("traefik_proxy")
        for site in sites:
            network_name = f"{site['name']}_isolated"
            try:
                network = docker_client.networks.get(network_name)
                networks = traefik.attrs['NetworkSettings']['Networks']
                if network_name not in networks:
                    network.connect(traefik)
                    print(f"🔗 Traefik podłączony do {network_name}")
            except docker.errors.NotFound:
                pass
            except docker.errors.APIError:
                pass
    except Exception as e:
        print(f"⚠️  Nie udało się podłączyć Traefik: {e}")
    
    for site in sites:
        site_name = site['name']
        site_id = site['id']
        
        limits = database.get_resource_limits(site_id)
        cpu_limit = limits['cpu_limit'] if limits else 50
        ram_limit = limits['ram_limit_mb'] if limits else 512
        
        try:
            container = docker_client.containers.get(site_name)
            if container.status != 'running':
                print(f"▶️  Uruchamiam zatrzymany kontener {site_name}...")
                container.start()
            else:
                print(f"✅ Kontener {site_name} już działa")
        except docker.errors.NotFound:
            print(f"🆕 Tworzę nowy kontener dla {site_name} (CPU: {cpu_limit}%, RAM: {ram_limit}MB)...")
            container = docker_manager.start_container(site_name, cpu_limit=cpu_limit, ram_limit_mb=ram_limit)
            if container:
                conn = database.get_connection()
                conn.execute('UPDATE sites SET container_id = ? WHERE name = ?', 
                           (container.short_id, site_name))
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"❌ Błąd uruchamiania {site_name}: {e}")

autostart_sites()


@app.route("/")
def index():
    sites = database.get_all_sites()
    return render_template("index.html", sites=sites)

@app.route("/create", methods=["POST"])
def create():
    site_name = request.form.get("site_name").strip().lower()
    uploaded_file = request.files.get("html_file")

    if not site_name.isalnum():
        return "Błąd: Nazwa tylko litery i cyfry!", 400

    site_path = os.path.join(USER_DATA_DIR, site_name)
    if os.path.exists(site_path):
        return "Błąd: Strona już istnieje!", 400
    os.makedirs(site_path)

    # ZIP lub zaglushka
    if uploaded_file and uploaded_file.filename.endswith(".zip"):
        zip_path = os.path.join(site_path, "upload.zip")
        uploaded_file.save(zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(site_path)
            os.remove(zip_path)
        except Exception as e:
            return f"Błąd rozpakowania archiwum: {e}", 500
    else:
        with open(os.path.join(site_path, "index.html"), "w") as f:
            f.write(f"<h1>Strona: {site_name}</h1><p>Czekam na zawartość...</p>")

    try:
        container = docker_manager.start_container(site_name, cpu_limit=50, ram_limit_mb=512)
        if container:
            domain = f"{site_name}.localhost"
            site_id = database.add_site(site_name, container.short_id, domain)
            database.set_resource_limits(site_id, cpu_limit=50, ram_limit_mb=512, disk_limit_mb=1024)
        else:
            return "Błąd Docker", 500
    except Exception as e:
        return f"Błąd krytyczny: {e}", 500

    return redirect(url_for("index"))


@app.route("/delete/<site_name>", methods=["POST"])
def delete(site_name):
    docker_manager.stop_container(site_name)
    database.remove_site(site_name)
    shutil.rmtree(os.path.join(USER_DATA_DIR, site_name), ignore_errors=True)
    return redirect(url_for("index"))


@app.route("/database")
def view_database():
    """Strona szczegółowych informacji o stronach"""
    docker_client = docker.from_env()
    sites = database.get_all_sites()
    
    sites_info = []
    for site in sites:
        site_name = site['name']
        site_path = os.path.join(USER_DATA_DIR, site_name)
        
        container_info = {
            'id': 'N/A',
            'status': 'Nie uruchomiony',
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
                        ext = os.path.splitext(file)[1].lower() or 'bez rozszerzenia'
                        file_types[ext] = file_types.get(ext, 0) + 1
                    except:
                        pass
        
        top_types = sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:5]
        
        sites_info.append({
            'name': site_name,
            'domain': f"{site_name}.localhost",
            'created_at': site['created_at'] if 'created_at' in site.keys() else 'N/A',
            'owner': site['user_id'] if site['user_id'] else 'System',
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
    """Strona monitoringu metryk"""
    sites_metrics = metrics_module.get_all_sites_metrics()
    return render_template("metrics.html", sites_metrics=sites_metrics)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
