FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-debug.txt ./
ARG REQUIREMENTS_FILE=requirements.txt
RUN pip install --no-cache-dir -r ${REQUIREMENTS_FILE}

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
