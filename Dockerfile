FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json ./
RUN corepack enable && yarn install
COPY frontend/ ./
ENV REACT_APP_BACKEND_URL=
RUN REACT_APP_BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ") yarn build

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/build ./frontend/build

# Generate build info file
RUN echo "{\"build_time\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\", \"python\": \"$(python --version)\"}" > /app/backend/build_info.json

WORKDIR /app/backend

EXPOSE 8000

CMD ["python", "server.py"]
