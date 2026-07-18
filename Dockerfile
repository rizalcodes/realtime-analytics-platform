FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 8050

# Default: run the FastAPI API. docker-compose overrides this to also start Dash.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
