FROM python:3.12-slim
WORKDIR /app
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY app app
COPY web web
RUN chmod -R a+rX app web
USER 1000:1000
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn","app.main:configured","--factory","--host","127.0.0.1","--port","5005","--no-access-log"]
