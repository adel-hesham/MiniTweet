"""user-service: register, login, and look up users."""
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
        claims = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired token")

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.isdigit():
        raise HTTPException(401, "invalid or expired token")
    user_id = int(sub)
    if user_id <= 0:
        raise HTTPException(401, "invalid or expired token")
    return claims


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
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.isdigit():
        raise HTTPException(401, "invalid or expired token")
    user = db.get(User, int(sub))
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
