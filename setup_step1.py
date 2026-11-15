#!/usr/bin/env python3
"""
MiniTweet v2 - Step 1: foundation + user-service (Python) + login screen.

Run it inside an empty (or existing) project folder, for example "minitweet-v2":

    python setup_step1.py              # create everything that is missing
    python setup_step1.py --dry-run    # show what would happen, change nothing
    python setup_step1.py -v           # also list files that were left alone
    python setup_step1.py --force      # also overwrite files you edited (a .bak copy is saved)

Safe to run again: files you have edited are left alone. A few shared files
(docker-compose.yml, nginx.conf, contracts, App.tsx ...) are "managed": later
steps replace them, and the old copy is always saved next to it as <name>.bak.
.env is created once with random secrets and never touched again (missing
keys are appended if a later step needs new ones).
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

# Files that later steps will replace (a .bak copy is saved first).
MANAGED = {
    "docker-compose.yml",
    ".env.example",
    "docs/contracts.md",
    "frontend/nginx.conf",
    "frontend/src/App.tsx",
    "frontend/src/api.ts",
    "frontend/src/components/SystemPanel.tsx",
}

FILES: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Root files
# ---------------------------------------------------------------------------
FILES[".env.example"] = r'''RABBITMQ_USER=minitweet
RABBITMQ_PASSWORD=change-me-rabbit
DB_PASSWORD=change-me-db
JWT_SECRET=change-me-to-a-long-random-string
'''

FILES[".gitignore"] = r'''.env
*.bak
node_modules/
dist/
__pycache__/
*.pyc
.venv/
.pytest_cache/
'''

FILES["README.md"] = r'''# MiniTweet

A small microservices app built to practice the full DevOps lifecycle.

- 5 small services (Python and Node.js), one Postgres database each
- REST between services, RabbitMQ events for "something happened"
- React frontend with a live view of the system

## Run it

```bash
docker compose up --build
```

- App: http://localhost:8080
- RabbitMQ dashboard: http://localhost:15672 (login is in your .env file)
- user-service API docs: http://localhost:8080/api/users/docs

The rules all services follow (token format, event format, log format) are in
`docs/contracts.md`.
'''

FILES["docs/contracts.md"] = r'''# Contracts

Services share no code. They only agree on the rules below, so a service can be
written in any language.

## Services and paths

| Service | Language | Public path (through nginx) |
|---|---|---|
| user-service | Python (FastAPI) | `/api/users/...` |
| tweet-service | Node.js (Express) | `/api/tweets/...` |
| like-service | Node.js (Express) | `/api/likes/...` |
| notification-service | Node.js (Express) | `/api/notifications/...` |
| monitor-service | Python (FastAPI) | `/api/monitor/...` |

Every service listens on port 8000 inside Docker and has:

- `GET /health`: is the process alive? (always 200 when running)
- `GET /ready`: can it do its job? (checks its database, 503 if not)

## Token (JWT)

- Created by user-service at login. Sent as `Authorization: Bearer <token>`.
- Algorithm HS256, signed with the secret from the `JWT_SECRET` environment variable.
- Claims: `sub` (user id as text), `username`, `iat`, `exp`.
- Every service checks the token itself with the same secret. No call to user-service.

## Errors

Failed requests answer with the right HTTP status and a body like `{"detail": "message"}`.

## Headers between services

- `X-Request-ID`: one id per user action. nginx creates it, services pass it on.
- `X-Caller`: when a service calls another service it sends its own name.

## Log format

One JSON object per line on the console (so ELK can read it later):

```json
{"timestamp": "2026-11-14T10:00:00+00:00", "level": "INFO", "service": "user-service",
 "message": "POST /api/users/login 200", "request_id": "ab12cd34ef56"}
```

Request lines also carry `method`, `path`, `status`, `duration_ms` and `caller`.

## Events (RabbitMQ)

- One topic exchange named `minitweet` (durable). The routing key is the event type.
- Messages are persistent JSON in this envelope:

```json
{"id": "uuid", "type": "tweet.liked", "time": "2026-11-14T10:00:00+00:00",
 "source": "like-service", "data": {}}
```

| Event | Sent by | Data | Received by |
|---|---|---|---|
| `user.registered` | user-service | `user_id`, `username` | notification, monitor |
| `tweet.created` | tweet-service | `tweet_id`, `user_id`, `username` | monitor |
| `tweet.deleted` | tweet-service | `tweet_id`, `user_id` | like, monitor |
| `tweet.liked` | like-service | `tweet_id`, `tweet_author_id`, `liked_by_id`, `liked_by_username` | notification, monitor |

Publishing is best effort: if RabbitMQ is down, the service logs a warning and the
main action still succeeds.
'''

FILES["docker-compose.yml"] = r'''name: minitweet

services:
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    restart: unless-stopped
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
    ports:
      - "15672:15672"   # RabbitMQ dashboard
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 10s
      retries: 10

  user-db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: users
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: users
    volumes:
      - user_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U users -d users"]
      interval: 5s
      timeout: 5s
      retries: 10

  user-service:
    build: ./services/user-service
    restart: unless-stopped
    environment:
      SERVICE_NAME: user-service
      DATABASE_URL: postgresql+psycopg2://users:${DB_PASSWORD}@user-db:5432/users
      RABBITMQ_URL: amqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@rabbitmq:5672/
      JWT_SECRET: ${JWT_SECRET}
    depends_on:
      user-db:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 15s

  frontend:
    build: ./frontend
    restart: unless-stopped
    ports:
      - "8080:80"
    depends_on:
      - user-service

volumes:
  user_db_data:
'''

# ---------------------------------------------------------------------------
# user-service (Python / FastAPI)
# ---------------------------------------------------------------------------
FILES["services/user-service/requirements.txt"] = r'''fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
psycopg2-binary==2.9.9
pika==1.3.2
PyJWT==2.9.0
bcrypt==4.2.0
'''

FILES["services/user-service/requirements-dev.txt"] = r'''pytest==8.3.3
httpx==0.27.2
'''

FILES["services/user-service/pytest.ini"] = r'''[pytest]
pythonpath = .
'''

FILES["services/user-service/.dockerignore"] = r'''tests
__pycache__
.pytest_cache
*.pyc
'''

FILES["services/user-service/Dockerfile"] = r'''FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
'''

FILES["services/user-service/app.py"] = r'''"""user-service: register, login, and look up users."""
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pika
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------- settings
SERVICE_NAME = os.getenv("SERVICE_NAME", "user-service")
DATABASE_URL = os.environ["DATABASE_URL"]
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "")
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
EXCHANGE = "minitweet"

# ----------------------------------------------------------------- logging
# One JSON object per line, same field names in every service (see docs/contracts.md).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(LOG_LEVEL.upper())
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False


setup_logging()
log = logging.getLogger(SERVICE_NAME)

# ---------------------------------------------------------------- database
engine_args: dict = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):  # only used by the tests
    engine_args = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(20), unique=True, nullable=False)
    password_hash = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create the tables. Retries because the database may still be starting."""
    for attempt in range(1, 31):
        try:
            Base.metadata.create_all(engine)
            log.info("database ready")
            return
        except Exception as exc:
            log.warning("database not ready (%s), retry %d/30", exc, attempt)
            time.sleep(2)
    raise RuntimeError("database never became ready")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


# ---------------------------------------------------------------- RabbitMQ
def _rabbit_params() -> pika.URLParameters:
    params = pika.URLParameters(RABBITMQ_URL)
    params.socket_timeout = 3
    return params


def rabbit_ok() -> bool:
    try:
        pika.BlockingConnection(_rabbit_params()).close()
        return True
    except Exception:
        return False


def publish_event(event_type: str, data: dict) -> None:
    """Best effort: if RabbitMQ is down we log a warning and carry on."""
    if not RABBITMQ_URL:
        return
    message = {
        "id": str(uuid.uuid4()),
        "type": event_type,
        "time": datetime.now(timezone.utc).isoformat(),
        "source": SERVICE_NAME,
        "data": data,
    }
    try:
        connection = pika.BlockingConnection(_rabbit_params())
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=event_type,
            body=json.dumps(message),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
        connection.close()
        log.info("event published: %s", event_type, extra={"fields": {"event_id": message["id"]}})
    except Exception as exc:
        log.warning("could not publish %s: %s", event_type, exc)


# -------------------------------------------------------------------- auth
def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_claims(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing token")
    try:
        return jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired token")


# --------------------------------------------------------------------- app
app = FastAPI(
    title="MiniTweet user-service",
    docs_url="/api/users/docs",
    openapi_url="/api/users/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request_id_var.set(request_id)
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        if not request.url.path.endswith(("/health", "/ready")):  # keep probes out of the logs
            log.info(
                "%s %s %s", request.method, request.url.path, status,
                extra={"fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "caller": request.headers.get("x-caller", "browser"),
                }},
            )


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=72)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=72)


@app.get("/health")
@app.get("/api/users/health", include_in_schema=False)
def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/ready")
@app.get("/api/users/ready", include_in_schema=False)
def ready(response: Response):
    # Ready means "I can do my job". RabbitMQ is reported but optional,
    # because publishing events is best effort.
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    if not RABBITMQ_URL:
        rabbitmq = "not configured"
    else:
        rabbitmq = "ok" if rabbit_ok() else "unavailable"
    if database != "ok":
        response.status_code = 503
    return {
        "status": "ready" if database == "ok" else "not ready",
        "checks": {"database": database, "rabbitmq": rabbitmq},
    }


@app.post("/api/users/register", status_code=201)
def register(body: Credentials, db: Session = Depends(get_db)):
    username = body.username.lower()
    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    user = User(username=username, password_hash=password_hash)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "username already taken")
    db.refresh(user)
    publish_event("user.registered", {"user_id": user.id, "username": user.username})
    return {"id": user.id, "username": user.username}


@app.post("/api/users/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username.lower()).first()
    if user is None or not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(401, "wrong username or password")
    return {
        "access_token": create_token(user),
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_MINUTES * 60,
    }


@app.get("/api/users/me")
def me(claims: dict = Depends(current_claims), db: Session = Depends(get_db)):
    user = db.get(User, int(claims["sub"]))
    if user is None:
        raise HTTPException(401, "user no longer exists")
    return {"id": user.id, "username": user.username, "created_at": user.created_at}


@app.get("/api/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Used by other services. Only public information."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    return {"id": user.id, "username": user.username}
'''

FILES["services/user-service/tests/test_app.py"] = r'''import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["RABBITMQ_URL"] = ""

import jwt
import pytest
from fastapi.testclient import TestClient

import app as user_app


@pytest.fixture()
def client(monkeypatch):
    sent = []
    monkeypatch.setattr(user_app, "publish_event", lambda event_type, data: sent.append((event_type, data)))
    user_app.Base.metadata.drop_all(user_app.engine)
    with TestClient(user_app.app) as test_client:
        test_client.sent_events = sent
        yield test_client


def register(client, username="adel", password="secret123"):
    return client.post("/api/users/register", json={"username": username, "password": password})


def login(client, username="adel", password="secret123"):
    return client.post("/api/users/login", json={"username": username, "password": password})


def test_register_creates_user_and_publishes_event(client):
    response = register(client)
    assert response.status_code == 201
    assert response.json()["username"] == "adel"
    event_type, data = client.sent_events[0]
    assert event_type == "user.registered"
    assert data["username"] == "adel"


def test_username_is_case_insensitive(client):
    assert register(client, "Adel").json()["username"] == "adel"
    assert register(client, "ADEL").status_code == 409


def test_duplicate_username_is_rejected(client):
    register(client)
    assert register(client).status_code == 409


def test_short_password_is_rejected(client):
    assert register(client, password="123").status_code == 422


def test_login_returns_valid_token(client):
    user_id = register(client).json()["id"]
    response = login(client)
    assert response.status_code == 200
    claims = jwt.decode(response.json()["access_token"], "test-secret", algorithms=["HS256"])
    assert claims["sub"] == str(user_id)
    assert claims["username"] == "adel"


def test_login_with_wrong_password_fails(client):
    register(client)
    assert login(client, password="wrong-password").status_code == 401


def test_me_requires_a_token(client):
    assert client.get("/api/users/me").status_code == 401


def test_me_returns_the_logged_in_user(client):
    register(client)
    token = login(client).json()["access_token"]
    response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "adel"


def test_get_user_by_id_is_public_and_minimal(client):
    user_id = register(client).json()["id"]
    response = client.get(f"/api/users/{user_id}")
    assert response.status_code == 200
    assert set(response.json()) == {"id", "username"}
    assert client.get("/api/users/9999").status_code == 404


def test_health_and_ready(client):
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"
'''

# ---------------------------------------------------------------------------
# frontend (React + TypeScript + Vite + Tailwind)
# ---------------------------------------------------------------------------
FILES["frontend/package.json"] = r'''{
  "name": "minitweet-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "typecheck": "tsc --noEmit",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.11",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.13",
    "typescript": "^5.6.2",
    "vite": "^5.4.8"
  }
}
'''

FILES["frontend/vite.config.ts"] = r'''import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// "npm run dev" talks to the Docker stack running on port 8080.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8080" } },
});
'''

FILES["frontend/tsconfig.json"] = r'''{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  },
  "include": ["src"]
}
'''

FILES["frontend/tailwind.config.js"] = r'''export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#5B5BF0", dark: "#4747D6" },
        accent: "#FF6B5B",
        surface: { DEFAULT: "#F7F8FC", dark: "#0B0F1A" },
        card: { DEFAULT: "#FFFFFF", dark: "#121828" },
        ink: { DEFAULT: "#111827", dark: "#E5E7EB" },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        heading: ['"Plus Jakarta Sans"', "Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
};
'''

FILES["frontend/postcss.config.js"] = r'''export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
'''

FILES["frontend/index.html"] = r'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MiniTweet</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
'''

FILES["frontend/Dockerfile"] = r'''# Stage 1: build the React app
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: serve it with nginx (which also forwards /api/... to the services)
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
'''

FILES["frontend/.dockerignore"] = r'''node_modules
dist
'''

FILES["frontend/nginx.conf"] = r'''server {
    listen 80;
    resolver 127.0.0.11 valid=10s ipv6=off;   # Docker's internal DNS
    root /usr/share/nginx/html;
    index index.html;

    location /api/users/ {
        set $user_service http://user-service:8000;
        proxy_pass $user_service;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Request-ID $request_id;
    }

    location / {
        try_files $uri /index.html;
    }
}
'''

FILES["frontend/src/vite-env.d.ts"] = r'''/// <reference types="vite/client" />
'''

FILES["frontend/src/index.css"] = r'''@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply font-sans antialiased;
  }
  h1, h2, h3 {
    @apply font-heading;
  }
}
'''

FILES["frontend/src/main.tsx"] = r'''import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
'''

FILES["frontend/src/api.ts"] = r'''export interface User {
  id: number;
  username: string;
  created_at?: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const TOKEN_KEY = "minitweet_token";
export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string): void => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = (): void => localStorage.removeItem(TOKEN_KEY);

function errorText(data: any): string {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return String(detail[0].msg);
  return "Something went wrong";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, errorText(data));
  return data as T;
}

export function register(username: string, password: string): Promise<User> {
  return request<User>("/users/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string): Promise<{ access_token: string }> {
  return request<{ access_token: string }>("/users/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function me(): Promise<User> {
  return request<User>("/users/me");
}

// Reads the claims inside a JWT (no verification, just for showing them on screen).
export function decodeToken(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}
'''

FILES["frontend/src/components/Logo.tsx"] = r'''export default function Logo() {
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-accent text-lg text-white shadow-md">
        ⚡
      </div>
      <span className="font-heading text-xl font-extrabold tracking-tight">MiniTweet</span>
    </div>
  );
}
'''

FILES["frontend/src/components/ThemeToggle.tsx"] = r'''import { useEffect, useState } from "react";

function startsDark(): boolean {
  const saved = localStorage.getItem("theme");
  if (saved) return saved === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export default function ThemeToggle() {
  const [dark, setDark] = useState<boolean>(startsDark);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <button
      onClick={() => setDark(!dark)}
      aria-label="Switch between light and dark mode"
      className="rounded-full p-2 text-lg transition hover:bg-black/5 dark:hover:bg-white/10"
    >
      {dark ? "☀️" : "🌙"}
    </button>
  );
}
'''

FILES["frontend/src/components/AuthPanel.tsx"] = r'''import { useState } from "react";
import type { FormEvent } from "react";

import { login, me, register, setToken } from "../api";
import type { User } from "../api";

interface Props {
  onAuthenticated: (user: User) => void;
}

const inputClass =
  "w-full rounded-xl border border-black/10 bg-white px-4 py-3 text-sm outline-none transition " +
  "focus:border-brand focus:ring-2 focus:ring-brand/30 dark:border-white/10 dark:bg-surface-dark";

export default function AuthPanel({ onAuthenticated }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") await register(username, password);
      const { access_token } = await login(username, password);
      setToken(access_token);
      onAuthenticated(await me());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const tab = (active: boolean) =>
    `flex-1 rounded-lg py-2 text-sm font-semibold transition ${
      active ? "bg-brand text-white shadow" : "opacity-70 hover:opacity-100"
    }`;

  return (
    <div className="rounded-2xl border border-black/5 bg-card p-6 shadow-sm dark:border-white/10 dark:bg-card-dark">
      <h2 className="text-2xl font-extrabold tracking-tight">
        {mode === "login" ? "Welcome back" : "Create your account"}
      </h2>
      <p className="mt-1 text-sm opacity-70">
        {mode === "login" ? "Log in to start tweeting." : "It takes a few seconds."}
      </p>

      <div className="mt-5 flex gap-1 rounded-xl bg-black/5 p-1 dark:bg-white/10">
        <button type="button" className={tab(mode === "login")} onClick={() => setMode("login")}>
          Log in
        </button>
        <button type="button" className={tab(mode === "register")} onClick={() => setMode("register")}>
          Sign up
        </button>
      </div>

      <form onSubmit={submit} className="mt-5 space-y-4">
        <input
          className={inputClass}
          placeholder="Username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <input
          className={inputClass}
          type="password"
          placeholder="Password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {mode === "register" && (
          <p className="text-xs opacity-60">3 to 20 letters, numbers or _ . Password: 6 or more characters.</p>
        )}
        {error && (
          <div className="rounded-xl bg-red-100 px-4 py-2 text-sm text-red-700 dark:bg-red-900/40 dark:text-red-300">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-xl bg-brand py-3 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:opacity-60"
        >
          {busy ? "Please wait..." : mode === "login" ? "Log in" : "Create account"}
        </button>
      </form>
    </div>
  );
}
'''

FILES["frontend/src/components/Profile.tsx"] = r'''import { decodeToken, getToken } from "../api";
import type { User } from "../api";

interface Props {
  user: User;
  onLogout: () => void;
}

export default function Profile({ user, onLogout }: Props) {
  const token = getToken() ?? "";
  const claims = decodeToken(token);
  const exp = claims && typeof claims.exp === "number" ? claims.exp : null;

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-black/5 bg-card p-6 shadow-sm dark:border-white/10 dark:bg-card-dark">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-brand to-accent text-2xl font-bold uppercase text-white">
              {user.username.charAt(0)}
            </div>
            <div>
              <h2 className="text-xl font-extrabold tracking-tight">@{user.username}</h2>
              <p className="text-sm opacity-70">User #{user.id}</p>
            </div>
          </div>
          <button
            onClick={onLogout}
            className="rounded-full border border-black/10 px-4 py-2 text-sm font-semibold transition hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          >
            Log out
          </button>
        </div>
        <p className="mt-4 rounded-xl bg-emerald-100 px-4 py-2 text-sm text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
          You are logged in. The feed arrives in step 2.
        </p>
      </div>

      <div className="rounded-2xl border border-black/5 bg-card p-6 shadow-sm dark:border-white/10 dark:bg-card-dark">
        <h3 className="text-lg font-bold">Your login token</h3>
        <p className="mt-1 text-sm opacity-70">
          This is what user-service gave you. Every other service will check it the same way.
          {exp !== null && ` Expires at ${new Date(exp * 1000).toLocaleTimeString()}.`}
        </p>
        <pre className="mt-3 overflow-x-auto rounded-xl bg-black/5 p-4 text-xs dark:bg-white/10">
          {JSON.stringify(claims, null, 2)}
        </pre>
      </div>
    </div>
  );
}
'''

FILES["frontend/src/components/SystemPanel.tsx"] = r'''const SERVICES = [
  { name: "user-service", tech: "Python", state: "built" },
  { name: "tweet-service", tech: "Node.js", state: "step 2" },
  { name: "like-service", tech: "Node.js", state: "step 3" },
  { name: "notification-service", tech: "Node.js", state: "step 4" },
  { name: "monitor-service", tech: "Python", state: "step 5" },
];

export default function SystemPanel() {
  return (
    <div className="rounded-2xl border border-black/5 bg-card p-6 shadow-sm dark:border-white/10 dark:bg-card-dark">
      <h2 className="text-2xl font-extrabold tracking-tight">Live system view</h2>
      <p className="mt-1 text-sm opacity-70">
        The live dashboard (service status, API requests and RabbitMQ messages) arrives in step 5.
        For now this shows the plan.
      </p>

      <ul className="mt-5 space-y-2">
        {SERVICES.map((service) => (
          <li
            key={service.name}
            className="flex items-center justify-between rounded-xl border border-black/5 px-4 py-3 dark:border-white/10"
          >
            <div>
              <p className="text-sm font-semibold">{service.name}</p>
              <p className="text-xs opacity-60">{service.tech}</p>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                service.state === "built"
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                  : "bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
              }`}
            >
              {service.state}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
'''

FILES["frontend/src/App.tsx"] = r'''import { useEffect, useState } from "react";

import { clearToken, getToken, me } from "./api";
import type { User } from "./api";
import AuthPanel from "./components/AuthPanel";
import Logo from "./components/Logo";
import Profile from "./components/Profile";
import SystemPanel from "./components/SystemPanel";
import ThemeToggle from "./components/ThemeToggle";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState<boolean>(getToken() !== null);
  const [tab, setTab] = useState<"app" | "system">("app");

  // If there is a saved token, find out who it belongs to.
  useEffect(() => {
    if (getToken() === null) return;
    me()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setChecking(false));
  }, []);

  function logout() {
    clearToken();
    setUser(null);
  }

  const tabClass = (active: boolean) =>
    `flex-1 py-3 text-sm font-semibold ${active ? "text-brand" : "opacity-60"}`;

  return (
    <div className="min-h-screen bg-surface pb-16 text-ink transition-colors dark:bg-surface-dark dark:text-ink-dark lg:pb-0">
      <header className="sticky top-0 z-10 border-b border-black/5 bg-surface/80 backdrop-blur dark:border-white/10 dark:bg-surface-dark/80">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <Logo />
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:grid-cols-2">
        <section className={tab === "app" ? "" : "hidden lg:block"}>
          {checking ? (
            <div className="h-48 animate-pulse rounded-2xl bg-black/5 dark:bg-white/10" />
          ) : user ? (
            <Profile user={user} onLogout={logout} />
          ) : (
            <AuthPanel onAuthenticated={setUser} />
          )}
        </section>
        <section className={tab === "system" ? "" : "hidden lg:block"}>
          <SystemPanel />
        </section>
      </main>

      <nav className="fixed bottom-0 left-0 right-0 flex border-t border-black/10 bg-surface dark:border-white/10 dark:bg-surface-dark lg:hidden">
        <button className={tabClass(tab === "app")} onClick={() => setTab("app")}>
          App
        </button>
        <button className={tabClass(tab === "system")} onClick={() => setTab("system")}>
          System
        </button>
      </nav>
    </div>
  );
}
'''


# ---------------------------------------------------------------------------
# Writing logic
# ---------------------------------------------------------------------------
def normalize(content: str) -> str:
    return content if content.endswith("\n") or content == "" else content + "\n"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:  # always LF line endings
        handle.write(content)


def generate_value(key: str) -> str | None:
    if key == "JWT_SECRET":
        return secrets.token_urlsafe(48)
    if key.endswith("PASSWORD"):
        return secrets.token_hex(16)
    return None


def sync_env(root: Path, example: str, dry_run: bool) -> None:
    """Create .env once; later steps only append keys that are missing."""
    env_path = root / ".env"
    wanted = [line.split("=", 1) for line in example.splitlines() if "=" in line]
    existing = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    have = {line.split("=", 1)[0] for line in existing if "=" in line}
    new_lines = []
    for key, value in wanted:
        if key not in have:
            new_lines.append(f"{key}={generate_value(key) or value}")
    if not new_lines:
        return
    action = "update" if env_path.exists() else "create"
    print(f"  {action:<9} .env  ({len(new_lines)} new value(s), secrets generated randomly)")
    if dry_run:
        return
    write_text(env_path, "\n".join(existing + new_lines) + "\n")
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="MiniTweet v2 - step 1 setup")
    parser.add_argument("--force", action="store_true", help="also overwrite files you edited (.bak saved)")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list files left alone")
    args = parser.parse_args()

    root = Path.cwd()
    counts = {"created": 0, "updated": 0, "kept": 0}
    print(f"MiniTweet step 1 in: {root}" + ("  [dry run]" if args.dry_run else ""))

    for rel, raw in FILES.items():
        content = normalize(raw)
        path = root / rel
        if not path.exists():
            action = "create"
        else:
            current = path.read_text(encoding="utf-8")
            if current == content:
                counts["kept"] += 1
                if args.verbose:
                    print(f"  same      {rel}")
                continue
            if rel not in MANAGED and not args.force:
                counts["kept"] += 1
                if args.verbose:
                    print(f"  keep      {rel}  (you edited it)")
                continue
            action = "update"
            if not args.dry_run:
                path.with_name(path.name + ".bak").write_text(current, encoding="utf-8")
        counts["created" if action == "create" else "updated"] += 1
        print(f"  {action:<9} {rel}" + ("  (old copy saved as .bak)" if action == "update" else ""))
        if not args.dry_run:
            write_text(path, content)

    sync_env(root, normalize(FILES[".env.example"]), args.dry_run)

    print(f"\nDone: {counts['created']} created, {counts['updated']} updated, {counts['kept']} already in place.")
    if not args.dry_run:
        print("\nNext:\n  docker compose up --build\n  then open http://localhost:8080")
    return 0


if __name__ == "__main__":
    sys.exit(main())
