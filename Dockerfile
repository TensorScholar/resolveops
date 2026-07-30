FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir '.[web]'
USER 65532:65532
EXPOSE 8080
CMD ["resolveops", "serve", "--host", "0.0.0.0", "--port", "8080"]
