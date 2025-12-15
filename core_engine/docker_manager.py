import docker
import time
import os

client = docker.from_env()


def create_isolated_network(name):
    """Створює ізольовану мережу для сайту та підключає Traefik"""
    network_name = f"{name}_isolated"
    try:
        # Перевіряємо чи існує мережа
        network = client.networks.get(network_name)
        print(f"   🔄 Мережа {network_name} вже існує")
    except docker.errors.NotFound:
        # Створюємо нову ізольовану мережу
        network = client.networks.create(
            network_name,
            driver="bridge",
            internal=False,  # False щоб мати доступ до інтернету
        )
        print(f"   🆕 Створено мережу {network_name}")
    
    # ВАЖЛИВО: Підключаємо Traefik до цієї мережі
    try:
        traefik = client.containers.get("traefik_proxy")
        # Перевіряємо чи вже підключений
        networks = traefik.attrs['NetworkSettings']['Networks']
        if network_name not in networks:
            network.connect(traefik)
            print(f"   🔗 Traefik підключено до {network_name}")
    except docker.errors.APIError as e:
        if "already exists" not in str(e):
            print(f"   ⚠️  Помилка підключення Traefik: {e}")
    except Exception as e:
        print(f"   ⚠️  Traefik недоступний: {e}")
    
    return network


def start_container(name, cpu_limit=50, ram_limit_mb=512):
    """
    Запускає ізольований контейнер з лімітами ресурсів.
    
    Args:
        name: Назва сайту/контейнера
        cpu_limit: Відсоток CPU (0-100), default 50%
        ram_limit_mb: Ліміт RAM у MB, default 512MB
    """
    host_project_path = os.environ.get("REAL_PROJECT_PATH")
    if not host_project_path:
        host_project_path = os.getcwd()

    abs_path_on_host = os.path.join(host_project_path, "user_data", name)
    domain = f"{name}.localhost"
    
    # Створюємо ізольовану мережу
    network = create_isolated_network(name)
    
    print(f"🚀 Запускаю {domain} (CPU: {cpu_limit}%, RAM: {ram_limit_mb}MB)")
    print(f"   📁 Путь: {abs_path_on_host}")
    print(f"   🔒 Мережа: {network.name} (ізольована)")

    try:
        container = client.containers.run(
            "nginx:latest",
            detach=True,
            name=name,
            network=network.name,  # Ізольована мережа
            restart_policy={"Name": "always"},
            # === ЛІМІТИ РЕСУРСІВ ===
            cpu_quota=int(cpu_limit * 1000),  # CPU ліміт (50% = 50000)
            cpu_period=100000,  # Базовий період
            mem_limit=f"{ram_limit_mb}m",  # RAM ліміт
            memswap_limit=f"{ram_limit_mb}m",  # Вимикаємо swap
            # === БЕЗПЕКА ===
            security_opt=["no-new-privileges:true"],  # Заборона підвищення привілеїв
            read_only=False,  # nginx потребує запису в /var/cache
            tmpfs={
                '/var/cache/nginx': 'size=10M,mode=1777',  # Тимчасова FS для кешу
                '/var/run': 'size=1M,mode=1777'
            },
            volumes={
                abs_path_on_host: {"bind": "/usr/share/nginx/html", "mode": "ro"}
            },
            labels={
                "traefik.enable": "true",
                f"traefik.http.routers.{name}.rule": f"Host(`{domain}`)",
                f"traefik.http.routers.{name}.entrypoints": "web",
                f"isolation.level": "full",
                f"resource.cpu": str(cpu_limit),
                f"resource.ram": str(ram_limit_mb),
            },
        )
        
        print(f"   ✅ Контейнер {name} запущено з повною ізоляцією")
        print(f"   🔒 Мережа: {network.name} (тільки Traefik має доступ)")
        
        return container

    except Exception as e:
        print(f"🔥 Помилка Docker: {e}")
        return None


def stop_container(name):
    """Зупиняє контейнер і видаляє його ізольовану мережу"""
    print(f"💀 Видаляю {name}...")
    
    try:
        container = client.containers.get(name)
        container.stop()
        container.remove()
        
        # Видаляємо ізольовану мережу
        network_name = f"{name}_isolated"
        try:
            network = client.networks.get(network_name)
            network.remove()
            print(f"   🗑️ Видалено мережу {network_name}")
        except docker.errors.NotFound:
            pass
            
    except Exception as e:
        print(f"Помилка видалення: {e}")
