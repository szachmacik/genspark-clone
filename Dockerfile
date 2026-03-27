FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn httpx pydantic python-multipart --no-cache-dir
COPY main.py main.py
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
