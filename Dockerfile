FROM python:3.12-slim

WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application
COPY backend/ backend/
COPY frontend/ frontend/
COPY scripts/ scripts/

RUN mkdir -p media

EXPOSE 8000

# Les tables sont créées automatiquement au démarrage (create_all).
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
