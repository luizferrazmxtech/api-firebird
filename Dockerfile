FROM python:3.10-slim

# Instala dependências do sistema
RUN apt-get update && apt-get install -y libpq5 && rm -rf /var/lib/apt/lists/*

# Cria diretório de trabalho
WORKDIR /app

# Copia os arquivos
COPY requirements.txt .

# Instala as dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante dos arquivos
COPY . .

# Comando pra rodar o app
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
