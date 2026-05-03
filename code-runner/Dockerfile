FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6 libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN useradd -m -u 1000 runner
RUN mkdir -p /tmp/code-output && chown runner:runner /tmp/code-output
USER runner

ENV MPLBACKEND=Agg

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
