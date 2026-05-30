FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
COPY web/ web/
RUN pip install -e ".[web]"
EXPOSE 8080
CMD ["python", "web/main.py"]
