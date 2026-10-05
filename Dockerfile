FROM python:3.12-slim
WORKDIR /app
COPY src/ src/
ENV HOST=0.0.0.0 PORT=8000 DATABASE_PATH=/data/calculator.db
EXPOSE 8000
CMD ["python", "src/server.py"]
