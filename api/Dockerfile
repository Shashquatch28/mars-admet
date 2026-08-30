FROM python:3.11-slim

WORKDIR /app

COPY contracts /contracts
COPY api/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -e /contracts \
    && pip install --no-cache-dir -r requirements.txt

COPY api/app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]