FROM python:3.10-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update -qq && apt-get install -y --fix-missing --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
RUN playwright install --with-deps chromium
COPY . .
EXPOSE 8020
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020"]