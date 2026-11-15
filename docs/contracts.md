# Contracts

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
