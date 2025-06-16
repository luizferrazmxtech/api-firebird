FROM python:3.10-slim

# Instala o cliente Firebird
RUN apt-get update && apt-get install -y \
    firebird-dev \
    libfbclient2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
