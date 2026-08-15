FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./api
COPY core /app/core
COPY api /app/api
EXPOSE 8000

# Cambiamos main:app por api.main:app
CMD ["uvicorn", "api.main:app", "--host", "0.0.0", "--port", "8000", "--reload"]