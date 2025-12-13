import docker
import time
import os

client = docker.from_env()


def start_container(name):
    """
    Запускает контейнер, используя НАСТОЯЩИЙ путь хоста.
    """
    # 1. Получаем путь к проекту на хосте из docker-compose
    host_project_path = os.environ.get("REAL_PROJECT_PATH")

    # Если переменной нет (запуск без докера), используем обычный путь
    if not host_project_path:
        host_project_path = os.getcwd()

    # 2. Формируем путь, который понятен ГЛАВНОМУ Докеру
    # Было: /app/user_data/name
    # Стало: /home/anton/hosting-project/user_data/name
    abs_path_on_host = os.path.join(host_project_path, "user_data", name)

    domain = f"{name}.localhost"
    print(f"🚀 Запускаю {domain}. Путь на хосте: {abs_path_on_host}")

    try:
        container = client.containers.run(
            "nginx:latest",
            detach=True,
            name=name,
            network="hosting_net",
            volumes={
                # ВАЖНО: Используем путь хоста!
                abs_path_on_host: {"bind": "/usr/share/nginx/html", "mode": "ro"}
            },
            labels={
                "traefik.enable": "true",
                f"traefik.http.routers.{name}.rule": f"Host(`{domain}`)",
                f"traefik.http.routers.{name}.entrypoints": "web",
            },
        )
        return container

    except Exception as e:
        print(f"🔥 Ошибка Docker: {e}")
        return None


def stop_container(name):
    # (Этот код остается без изменений - копировать старый)
    print(f"💀 Удаляю {name}...")
    try:
        container = client.containers.get(name)
        container.stop()
        container.remove()
    except Exception as e:
        print(f"Ошибка удаления: {e}")
