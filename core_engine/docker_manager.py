import docker
import time
import os

client = docker.from_env()


def create_isolated_network(name):
    """Tworzy izolowaną sieć dla strony i łączy z Traefik"""
    network_name = f"{name}_isolated"
    try:
        network = client.networks.get(network_name)
        print(f"   🔄 Sieć {network_name} już istnieje")
    except docker.errors.NotFound:
        network = client.networks.create(
            network_name,
            driver="bridge",
            internal=False,
        )
        print(f"   🆕 Utworzono sieć {network_name}")
    
    # Połączenie Traefik z izolowaną siecią
    try:
        traefik = client.containers.get("traefik_proxy")
        networks = traefik.attrs['NetworkSettings']['Networks']
        if network_name not in networks:
            network.connect(traefik)
            print(f"   🔗 Traefik podłączony do {network_name}")
    except docker.errors.APIError as e:
        if "already exists" not in str(e):
            print(f"   ⚠️  Błąd połączenia Traefik: {e}")
    except Exception as e:
        print(f"   ⚠️  Traefik niedostępny: {e}")
    
    return network


def start_container(name, cpu_limit=50, ram_limit_mb=512):
    """Uruchamia izolowany kontener z limitami zasobów"""
    host_project_path = os.environ.get("REAL_PROJECT_PATH")
    if not host_project_path:
        host_project_path = os.getcwd()

    abs_path_on_host = os.path.join(host_project_path, "user_data", name)
    domain = f"{name}.localhost"
    
    network = create_isolated_network(name)
    
    print(f"🚀 Uruchamiam {domain} (CPU: {cpu_limit}%, RAM: {ram_limit_mb}MB)")
    print(f"   📁 Ścieżka: {abs_path_on_host}")
    print(f"   🔒 Sieć: {network.name} (izolowana)")

    try:
        container = client.containers.run(
            "nginx:latest",
            detach=True,
            name=name,
            network=network.name,
            restart_policy={"Name": "always"},
            cpu_quota=int(cpu_limit * 1000),
            cpu_period=100000,
            mem_limit=f"{ram_limit_mb}m",
            memswap_limit=f"{ram_limit_mb}m",
            security_opt=["no-new-privileges:true"],
            read_only=False,
            tmpfs={
                '/var/cache/nginx': 'size=10M,mode=1777',
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
        
        print(f"   ✅ Kontener {name} uruchomiony z pełną izolacją")
        print(f"   🔒 Sieć: {network.name} (tylko Traefik ma dostęp)")
        
        return container

    except Exception as e:
        print(f"🔥 Błąd Docker: {e}")
        return None


def stop_container(name):
    """Zatrzymuje kontener i usuwa jego izolowaną sieć"""
    print(f"💀 Usuwam {name}...")
    
    try:
        container = client.containers.get(name)
        container.stop()
        container.remove()
        
        network_name = f"{name}_isolated"
        try:
            network = client.networks.get(network_name)
            network.remove()
            print(f"   🗑️ Usunięto sieć {network_name}")
        except docker.errors.NotFound:
            pass
            
    except Exception as e:
        print(f"Błąd usuwania: {e}")
