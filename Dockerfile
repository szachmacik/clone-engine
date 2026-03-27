FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn httpx pydantic --no-cache-dir
COPY main.py main.py
COPY schema.sql schema.sql
COPY static/ static/
COPY entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh
EXPOSE 9000
CMD ["/bin/bash", "entrypoint.sh"]
