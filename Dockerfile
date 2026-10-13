FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 EZAPU_DB=/datos/ezapu.db PORT=5000

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

VOLUME ["/datos"]
EXPOSE 5000

# Crea la base con datos de ejemplo si no existe y arranca el servidor.
CMD ["sh", "-c", "python -c \"from ezapu import db; import os; p=os.environ['EZAPU_DB']; db.init_db(p, seed=True)\" && python run.py"]
