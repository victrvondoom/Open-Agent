FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV HOST=0.0.0.0 PORT=8360
EXPOSE 8360
CMD ["python3", "-m", "payproof.server"]
