FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# requirements_cloud.txt referencia requirements.txt,
# então os dois precisam existir antes do pip install.
COPY requirements.txt requirements_cloud.txt ./

RUN pip install --no-cache-dir -r requirements_cloud.txt gunicorn

COPY . .

EXPOSE 8080

CMD ["/bin/sh", "-c", "exec gunicorn -w 1 --threads 4 -b 0.0.0.0:${PORT:-8080} cloud_entry:app"]
