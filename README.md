# MiniTweet

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
