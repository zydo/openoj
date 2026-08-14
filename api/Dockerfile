ARG PYTHON_VERSION="3.14.7"

FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN groupadd --gid 10001 openoj \
    && useradd --uid 10001 --gid openoj --no-create-home openoj \
    && mkdir -p /data /queue \
    && chown -R openoj:openoj /data /queue /app \
    && chmod 0700 /data \
    && chmod 0770 /queue

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
