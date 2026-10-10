# Small image that runs the pipeline once and exits.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt   # install dependencies first so Docker can cache this layer
COPY pipeline ./pipeline
COPY tests/fixtures ./tests/fixtures
CMD ["python", "-m", "pipeline.run"]
