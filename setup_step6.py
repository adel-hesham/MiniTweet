#!/usr/bin/env python3
"""
MiniTweet v2 - Step 6: tests runner, end-to-end smoke test, README and contracts.

Run it in the same folder where step 5 already works:

    python setup_step6.py              # add everything for step 6
    python setup_step6.py --dry-run    # show what would happen, change nothing
    python setup_step6.py -v           # also list files that were left alone
    python setup_step6.py --force      # also overwrite files you edited (a .bak copy is saved)

Safe to run again. README.md and docs/contracts.md are replaced (the old copy is
saved as <name>.bak). The scripts are only created if they do not exist yet.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Files from earlier steps that step 6 replaces (a .bak copy is saved first).
MANAGED = {
    "README.md",
    "docs/contracts.md",
}

FILES: dict[str, str] = {}

# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------
FILES["README.md"] = r'''# MiniTweet

A small microservices app built to practice the full DevOps lifecycle:
Git, Docker, CI/CD, testing, Kubernetes, Helm, Terraform, and secure service design.

It is a tiny Twitter clone: sign up, post tweets, like them, and see notifications.
The app is intentionally focused on the core product and clean service boundaries.

```
                    Browser (React)
                         │
                  frontend (nginx)  ── serves the app and forwards /api/... to the services
   ┌──────────┬──────────┬───────────┬────────────────┐
   ▼          ▼          ▼           ▼                │
 user ◄──── tweet ◄──── like    notification           │ REST
 Python     Node.js     Node.js    Node.js              │
   │          │          │           ▲                │
   DB         DB         DB          │ events          │
   └──────────┴──────────┴─── RabbitMQ ───────────────┘
```

| Service | Language | What it does | Database |
|---|---|---|---|
| user-service | Python (FastAPI) | register, login, token, user lookup | users |
| tweet-service | Node.js (Express) | post, list, delete tweets | tweets |
| like-service | Node.js (Express) | like and unlike, counts | likes |
| notification-service | Node.js (Express) | notifications from events | notifications |
| frontend | React + TypeScript + Tailwind, served by nginx | the app UI | none |

Each service has its own small Postgres database. Services never read each other's
databases: they use REST ("I need an answer now") or RabbitMQ events ("something happened").

## Run it

```bash
python setup_step1.py   # ... through setup_step6.py, once, in order (creates all the files and a .env)
docker compose up --build
```

| What | Where |
|---|---|
| The app | http://localhost:8080 |
| user-service API docs (Swagger) | http://localhost:8080/api/users/docs |
| RabbitMQ dashboard | http://localhost:15672 (login is in `.env`) |

The Node services have no auto-generated docs. Their endpoints are in the table below.

Stop everything with `Ctrl+C`. Reset all data with `docker compose down -v`.

## Tests

```bash
python scripts/run_tests.py             # unit tests of every service + the frontend type check
python scripts/run_tests.py --only like-service
python scripts/smoke_test.py            # end-to-end check against the running stack
```

- Python services use `pytest`, Node services use the built-in `node --test`.
- The unit tests use fakes, so they do not need Docker.
- The smoke test needs the stack running (`docker compose up`). It signs up two users,
  posts, likes, checks the notification, and cleans up.
  It uses only the Python standard library, so it is easy to run in a CI pipeline.

## API quick reference

All paths go through nginx on port 8080. Send `Authorization: Bearer <token>` where marked.

| Service | Endpoints |
|---|---|
| user | `POST /api/users/register`, `POST /api/users/login`, `GET /api/users/me` (token), `GET /api/users/{id}` |
| tweet | `GET /api/tweets`, `GET /api/tweets/{id}`, `POST /api/tweets` (token), `DELETE /api/tweets/{id}` (token, owner only) |
| like | `POST /api/likes` (token), `DELETE /api/likes/{tweet_id}` (token), `GET /api/likes?tweet_ids=1,2` (token) |
| notification | `GET /api/notifications` (token), `POST /api/notifications/read` (token) |

Every service also has `GET /health` (is it alive?) and `GET /ready` (can it do its job?).
Those two are the checks Docker and Kubernetes use.

## Project layout

```
minitweet/
├── docker-compose.yml        all containers
├── .env                      secrets (created by the setup script, never commit it)
├── docs/contracts.md         the rules every service follows (token, events, logs, headers)
├── scripts/                  run_tests.py, smoke_test.py
├── services/
│   ├── user-service/         app.py, Dockerfile, tests/
│   ├── tweet-service/        src/, Dockerfile, test/
│   ├── like-service/
│   ├── notification-service/
│   └── user-service/
└── frontend/                 React app, nginx.conf, Dockerfile
```

## Built for the DevOps work

| Every service has | So you can practice |
|---|---|
| `/health` and `/ready` | Docker health checks, Kubernetes liveness and readiness probes |
| all settings from environment variables | Compose `.env`, Kubernetes ConfigMaps and Secrets, Helm values |
| JSON logs, one line per event, same fields everywhere, a `request_id` that follows a click across services | ELK or Loki, searching one request across services |
| a small Dockerfile, non-root user | image scanning (Trivy), multi-stage builds, image size |
| its own tests | CI pipelines, one job per service |
| its own folder, image and database | per-service pipelines, versioning, a registry, StatefulSets, volumes |

### Monitoring is intentionally deferred

This version keeps the app focused on the core product. We are intentionally skipping the
monitoring layer for now and will add it later with ELK, Prometheus and Grafana.

Ideas for what to do next, roughly in order:

1. **Git:** a repository, branches, pull requests, a good `.gitignore`.
2. **CI:** one pipeline job per service (`pytest` or `npm test`), then build the images and run `scripts/smoke_test.py` against the Compose stack.
3. **Images:** version tags, a registry, Trivy scans, Gitleaks for secrets.
4. **Kubernetes:** a Deployment and Service for each app, a StatefulSet for each database, RabbitMQ, Ingress instead of the nginx proxy, probes on `/health` and `/ready`, Secrets for `DB_PASSWORD` and `JWT_SECRET`.
5. **Helm:** one chart with the five services as values.
6. **Terraform:** the cluster, registry and network around it.
7. **Monitoring (later):** ELK stack, Prometheus and Grafana, plus metrics endpoints and log shipping.
8. **DevSecOps:** SAST (Semgrep), dependency and image scans, network policies, secret management.

## Known simplifications

These are deliberate, to keep the app easy to understand. Each one is a good exercise.

- One shared `JWT_SECRET` (HS256). Any service could mint tokens. No refresh tokens, and a stolen token works until it expires (1 hour).
- No login rate limiting.
- RabbitMQ publishing is best effort. If RabbitMQ is down, the action succeeds and the event is lost. There are no outbox, dead-letter queues or long retries.
- Every service listens on plain HTTP inside the network. No TLS, no network policies yet.
- The database passwords all come from one `DB_PASSWORD` (each database is still separate).
- The frontend runs as a built static site behind nginx. There are no frontend unit tests, only a type check.
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
Health and ready checks are not logged.

## Events (RabbitMQ)

- One topic exchange named `minitweet` (durable). The routing key is the event type.
- Messages are persistent JSON in this envelope:

```json
{"id": "uuid", "type": "tweet.liked", "time": "2026-11-14T10:00:00+00:00",
 "source": "like-service", "data": {}}
```

| Event | Sent by | Data | Received by |
|---|---|---|---|
| `user.registered` | user-service | `user_id`, `username` | notification |
| `tweet.created` | tweet-service | `tweet_id`, `user_id`, `username` | none |
| `tweet.deleted` | tweet-service | `tweet_id`, `user_id` | like |
| `tweet.liked` | like-service | `tweet_id`, `tweet_author_id`, `liked_by_id`, `liked_by_username` | notification |

Rules for services that receive events:

- Each receiver has its own durable queue, so events wait if the receiver is down.
- Acknowledge only after the work is done. If handling fails, try once more, then drop the message.
- The same event can arrive twice. Handling it twice must not do harm (notification-service
  remembers the event id).

Publishing is best effort: if RabbitMQ is down, the service logs a warning and the
main action still succeeds.

## Monitoring is intentionally deferred

This version does not include a monitoring service yet. We will add ELK, Prometheus and
Grafana in a later stage, after the core app is stable.
'''

# ---------------------------------------------------------------------------
# contracts
# ---------------------------------------------------------------------------
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
Health and ready checks are not logged.

## Events (RabbitMQ)

- One topic exchange named `minitweet` (durable). The routing key is the event type.
- Messages are persistent JSON in this envelope:

```json
{"id": "uuid", "type": "tweet.liked", "time": "2026-11-14T10:00:00+00:00",
 "source": "like-service", "data": {}}
```

| Event | Sent by | Data | Received by (queue) |
|---|---|---|---|
| `user.registered` | user-service | `user_id`, `username` | notification (`notification-service.events`), monitor |
| `tweet.created` | tweet-service | `tweet_id`, `user_id`, `username` | monitor |
| `tweet.deleted` | tweet-service | `tweet_id`, `user_id` | like (`like-service.events`), monitor |
| `tweet.liked` | like-service | `tweet_id`, `tweet_author_id`, `liked_by_id`, `liked_by_username` | notification, monitor |

Rules for services that receive events:

- Each receiver has its own durable queue, so events wait if the receiver is down.
- Acknowledge only after the work is done. If handling fails, try once more, then drop the message.
- The same event can arrive twice. Handling it twice must not do harm (notification-service
  remembers the event id).

Publishing is best effort: if RabbitMQ is down, the service logs a warning and the
main action still succeeds.

## Monitoring (the live system view)

- Every service except monitor-service reports each request it handles (health and ready
  checks excluded) with `POST $MONITOR_URL/api/monitor/ingest/request`:

```json
{"time": "2026-11-14T10:00:00.250Z", "service": "tweet-service", "caller": "like-service",
 "method": "GET", "path": "/api/tweets/5", "status": 200, "duration_ms": 4.2, "request_id": "ab12cd34ef56"}
```

- It is fire and forget with a 1 second timeout. If `MONITOR_URL` is not set or
  monitor-service is down, nothing happens and the real request is not affected.
- `caller` is the `X-Caller` header, or `browser` when there is none.
- monitor-service checks `GET /ready` on every service every 3 seconds, listens to all
  events (routing key `#`), and keeps the latest 500 requests and 500 events.
- nginx answers 403 for `/api/monitor/ingest/...`, so only services inside the Docker network can report.
- The dashboard data (`GET /api/monitor/overview`) is public in this version.
'''

# ---------------------------------------------------------------------------
# scripts
# ---------------------------------------------------------------------------
FILES["scripts/run_tests.py"] = r'''#!/usr/bin/env python3
"""
Runs the unit tests of every service, then the frontend type check.

    python scripts/run_tests.py                   # everything
    python scripts/run_tests.py --only like-service
    python scripts/run_tests.py --install         # install dependencies first (pip / npm)

Python services use pytest (pip install -r requirements.txt -r requirements-dev.txt).
Node services use "npm test". Missing npm packages are installed automatically.
Exit code is 0 only if everything passed, so it can be used in a CI pipeline.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def discover():
    found = []
    services = ROOT / "services"
    if services.is_dir():
        for folder in sorted(services.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            if (folder / "package.json").exists():
                found.append((folder.name, folder, "node"))
            elif (folder / "requirements.txt").exists():
                found.append((folder.name, folder, "python"))
    if (ROOT / "frontend" / "package.json").exists():
        found.append(("frontend (type check)", ROOT / "frontend", "frontend"))
    return found


def run(command, cwd):
    print("  $ " + " ".join(str(part) for part in command))
    try:
        return subprocess.call(command, cwd=cwd)
    except FileNotFoundError as err:
        print(f"  cannot run: {err}")
        return 1


def run_one(kind, folder, install):
    if kind == "python":
        if install:
            code = run([sys.executable, "-m", "pip", "install", "-q",
                        "-r", "requirements.txt", "-r", "requirements-dev.txt"], folder)
            if code != 0:
                return False
        code = run([sys.executable, "-m", "pytest", "-q"], folder)
        if code != 0 and not install:
            print("  (if pytest or a package is missing, run again with --install)")
        return code == 0

    npm = shutil.which("npm")
    if npm is None:
        print("  npm was not found. Install Node.js 20 or newer.")
        return False
    if install or not (folder / "node_modules").exists():
        if run([npm, "install", "--no-audit", "--no-fund"], folder) != 0:
            return False
    return run([npm, "run", "typecheck"] if kind == "frontend" else [npm, "test"], folder) == 0


def main():
    parser = argparse.ArgumentParser(description="Run all MiniTweet tests")
    parser.add_argument("--only", help="run just one service, for example like-service")
    parser.add_argument("--install", action="store_true", help="install dependencies first")
    args = parser.parse_args()

    targets = discover()
    if args.only:
        targets = [t for t in targets if t[0].startswith(args.only)]
    if not targets:
        print("Nothing to test here. Run this from the minitweet folder.")
        return 1

    results = []
    for name, folder, kind in targets:
        print(f"\n=== {name} ===")
        results.append((name, run_one(kind, folder, args.install)))

    print("\n=== summary ===")
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
'''

FILES["scripts/smoke_test.py"] = r'''#!/usr/bin/env python3
"""
End-to-end check of a running MiniTweet stack. Uses only the Python standard library.

    docker compose up -d --build
    python scripts/smoke_test.py                       # checks http://localhost:8080
    python scripts/smoke_test.py http://some-host:8080

It signs up two new users, posts a tweet, likes it, waits for the notification, checks the
dashboard data, then deletes the tweet and checks the likes are cleaned up by the event.
Exit code is 0 only if every check passed, so it can be used in a CI pipeline.
"""
import json
import random
import string
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
failures = []


def call(method, path, body=None, token=None):
    """Returns (http status, parsed JSON or None). Status 0 means the server could not be reached."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        raw = err.read()
        try:
            return err.code, json.loads(raw)
        except ValueError:
            return err.code, None
    except Exception as err:
        return 0, {"error": str(err)}


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok or not detail else f"   ({detail})"))
    if not ok:
        failures.append(name)
    return ok


def wait_for(fn, seconds=15):
    """Keeps calling fn until it returns something truthy, or the time is up."""
    end = time.time() + seconds
    while time.time() < end:
        result = fn()
        if result:
            return result
        time.sleep(0.5)
    return None


def main():
    print(f"Smoke test against {BASE}\n")

    # 1. Is everything ready?
    for service in ("users", "tweets", "likes", "notifications", "monitor"):
        status, _ = call("GET", f"/api/{service}/ready")
        check(f"{service} service is ready", status == 200, f"HTTP {status}")
    if failures:
        print("\nThe stack is not ready. Is `docker compose up` finished?")
        return 1

    # 2. Two users
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    alice, bob = f"alice_{suffix}", f"bob_{suffix}"
    tokens = {}
    for name in (alice, bob):
        status, _ = call("POST", "/api/users/register", {"username": name, "password": "secret123"})
        check(f"register {name}", status == 201, f"HTTP {status}")
        status, body = call("POST", "/api/users/login", {"username": name, "password": "secret123"})
        check(f"login {name}", status == 200 and body and "access_token" in body, f"HTTP {status}")
        tokens[name] = (body or {}).get("access_token")
    if not all(tokens.values()):
        return 1
    ta, tb = tokens[alice], tokens[bob]

    status, _ = call("POST", "/api/users/login", {"username": alice, "password": "wrong-password"})
    check("a wrong password is refused", status == 401, f"HTTP {status}")

    # 3. Bob tweets
    status, _ = call("POST", "/api/tweets", {"content": "no token"})
    check("posting without a token is refused", status == 401, f"HTTP {status}")
    status, tweet = call("POST", "/api/tweets", {"content": f"hello from {bob}"}, tb)
    if not check("bob posts a tweet", status == 201 and tweet and "id" in tweet, f"HTTP {status}"):
        return 1
    tweet_id = tweet["id"]
    status, listing = call("GET", "/api/tweets?limit=50")
    check("the tweet is in the public list", status == 200 and any(t["id"] == tweet_id for t in listing or []))

    # 4. Alice likes it (REST: like-service asks tweet-service; event: tweet.liked)
    status, body = call("POST", "/api/likes", {"tweet_id": tweet_id}, ta)
    check("alice likes the tweet", status == 201 and body and body["count"] == 1, f"HTTP {status}")
    status, body = call("POST", "/api/likes", {"tweet_id": tweet_id}, ta)
    check("liking twice keeps one like", status == 200 and body and body["count"] == 1, f"HTTP {status}")
    status, body = call("GET", f"/api/likes?tweet_ids={tweet_id}", token=ta)
    check("alice sees her like in the summary",
          status == 200 and body and body[str(tweet_id)] == {"count": 1, "liked_by_me": True})
    status, body = call("POST", "/api/likes", {"tweet_id": 99999999}, ta)
    check("liking a tweet that does not exist gives 404", status == 404, f"HTTP {status}")

    # 5. The event arrives: bob gets notifications
    def bob_notifications():
        code, data = call("GET", "/api/notifications", token=tb)
        types = {n["type"] for n in (data or {}).get("notifications", [])} if code == 200 else set()
        return data if {"welcome", "like"} <= types else None

    data = wait_for(bob_notifications)
    check("bob gets a welcome and a like notification (events work)", data is not None)
    if data:
        like = next(n for n in data["notifications"] if n["type"] == "like")
        check("the like notification names alice", alice in like["message"], like["message"])
        status, after = call("POST", "/api/notifications/read", token=tb)
        check("bob can mark notifications as read", status == 200 and after == {"unread": 0}, f"HTTP {status}")

    # 6. Ownership rule
    status, _ = call("DELETE", f"/api/tweets/{tweet_id}", token=ta)
    check("alice cannot delete bob's tweet", status == 403, f"HTTP {status}")

    # 7. The dashboard saw it all
    def dashboard():
        code, data = call("GET", "/api/monitor/overview?limit=100")
        if code != 200:
            return None
        event_types = {e["type"] for e in data["events"]}
        calls = {(r["caller"], r["service"]) for r in data["requests"]}
        wanted_events = {"user.registered", "tweet.created", "tweet.liked"}
        wanted_calls = {("tweet-service", "user-service"), ("like-service", "tweet-service")}
        known = [s for s in data["status"] if s["status"] != "unknown"]
        if wanted_events <= event_types and wanted_calls <= calls and known:
            return data
        return None

    data = wait_for(dashboard)
    check("the dashboard shows the events and the service-to-service calls", data is not None)
    if data:
        down = [s["name"] for s in data["status"] if s["status"] == "down"]
        check("no service is reported as down", not down, ", ".join(down))
    status, _ = call("POST", "/api/monitor/ingest/request", {"service": "x"})
    check("the ingest door is closed from the outside", status == 403, f"HTTP {status}")

    # 8. Unlike, like again, then delete the tweet: the event removes the likes
    status, body = call("DELETE", f"/api/likes/{tweet_id}", token=ta)
    check("alice unlikes", status == 200 and body and body["count"] == 0, f"HTTP {status}")
    call("POST", "/api/likes", {"tweet_id": tweet_id}, ta)
    status, _ = call("DELETE", f"/api/tweets/{tweet_id}", token=tb)
    check("bob deletes his tweet", status == 204, f"HTTP {status}")
    status, _ = call("GET", f"/api/tweets/{tweet_id}")
    check("the deleted tweet is gone", status == 404, f"HTTP {status}")

    def likes_removed():
        code, body = call("GET", f"/api/likes?tweet_ids={tweet_id}", token=ta)
        return code == 200 and body and body[str(tweet_id)]["count"] == 0

    check("the likes of the deleted tweet are removed (tweet.deleted event)", bool(wait_for(likes_removed)))

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for name in failures:
            print(f"  - {name}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
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


def main() -> int:
    parser = argparse.ArgumentParser(description="MiniTweet v2 - step 6 setup")
    parser.add_argument("--force", action="store_true", help="also overwrite files you edited (.bak saved)")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list files left alone")
    args = parser.parse_args()

    root = Path.cwd()
    if not (root / "services" / "monitor-service" / "app.py").exists() or not (root / "docker-compose.yml").exists():
        print("Step 5 is not in this folder. Run this script inside the folder where step 5 works.")
        return 1

    counts = {"created": 0, "updated": 0, "kept": 0}
    print(f"MiniTweet step 6 in: {root}" + ("  [dry run]" if args.dry_run else ""))

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

    print(f"\nDone: {counts['created']} created, {counts['updated']} updated, {counts['kept']} already in place.")
    if not args.dry_run:
        print("\nNext:\n  python scripts/run_tests.py\n  docker compose up --build   (then in another terminal)\n  python scripts/smoke_test.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
