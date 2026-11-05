FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir confluent-kafka==2.8.2 psycopg[binary]==3.2.9
COPY consumer.py bot_listener.py ./
CMD ["python", "-u", "consumer.py"]
