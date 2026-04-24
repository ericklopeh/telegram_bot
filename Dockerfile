FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-docker.txt /app/requirements-docker.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements-docker.txt

COPY . /app

# -m: sys.path incluye /app; `python app/main.py` deja /app/app y falla `import app.*`
CMD ["python", "-m", "app.main"]
