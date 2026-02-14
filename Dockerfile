FROM python:3.10-slim

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libmp3lame-dev \
    libsndfile1 \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Créer le dossier de travail
WORKDIR /app

# Copier les fichiers de dépendances
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier tout le projet
COPY . .

# Créer les dossiers nécessaires
RUN mkdir -p uploads separated

# Exposer le port
EXPOSE 10000

# Commande de démarrage
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--timeout", "300"]

