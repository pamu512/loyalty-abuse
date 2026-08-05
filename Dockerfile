FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY adapters ./adapters
COPY static ./static
COPY contracts ./contracts
RUN pip install --no-cache-dir .
ENV PYTHONPATH=/app:/app/src
ENV LOYALTY_ABUSE_DB=/data/loyalty.db
EXPOSE 8080
CMD ["uvicorn", "loyalty_abuse_api.app:app", "--host", "0.0.0.0", "--port", "8080"]
