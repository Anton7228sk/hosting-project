# Используем легкий Python
FROM python:3.9-slim

# Рабочая папка внутри контейнера
WORKDIR /app

# Копируем список библиотек и устанавливаем их
COPY requirements.txt .
RUN pip install -r requirements.txt

# Копируем весь код проекта внутрь
COPY . .

# Запускаем приложение как модуль
CMD ["python", "-m", "web_panel.app"]