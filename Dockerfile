FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json ./
RUN corepack enable && yarn install
COPY frontend/ ./
ENV REACT_APP_BACKEND_URL=
RUN yarn build

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/build ./frontend/build

WORKDIR /app/backend

EXPOSE 8000

CMD ["python", "server.py"]
