FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn httpx pydantic --no-cache-dir
COPY main.py main.py
COPY static/ static/
EXPOSE 9000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000", "--workers", "2"]
