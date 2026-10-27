FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8360
# No third-party dependencies: the project uses the Python standard library only.
COPY . .
RUN mkdir -p /app/logs
EXPOSE 8360
CMD ["python3", "run.py"]
