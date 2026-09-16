FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 VOXPOP_DB=/data/voxpop.db
RUN pip install --no-cache-dir uv
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt
COPY . .
RUN mkdir -p /data
EXPOSE 8000
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8000"]
