FROM node:24-alpine AS web-build

WORKDIR /web
COPY services/web/package.json services/web/package-lock.json ./
RUN npm ci
COPY services/web/index.html services/web/vite.config.js ./
COPY services/web/src ./src
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

COPY services/api/requirements.txt services/api/requirements-debug.txt ./
ARG REQUIREMENTS_FILE=requirements.txt
RUN pip install --no-cache-dir -r ${REQUIREMENTS_FILE}

COPY services/api/app ./app
COPY --from=web-build /web/dist /web/dist

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
