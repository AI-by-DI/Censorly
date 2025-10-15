FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# tüm repo içeriğini kopyala
COPY . .

# main.py'nin yolu apps/worker/main.py
CMD ["python", "apps/worker/main.py"]