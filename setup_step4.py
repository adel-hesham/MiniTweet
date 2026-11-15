#!/usr/bin/env python3
"""
MiniTweet v2 - Step 4: notification-service (Node.js) + notifications tab.

Run it in the same folder where step 3 already works:

    python setup_step4.py              # add everything for step 4
    python setup_step4.py --dry-run    # show what would happen, change nothing
    python setup_step4.py -v           # also list files that were left alone
    python setup_step4.py --force      # also overwrite files you edited (a .bak copy is saved)

Safe to run again. Shared files that step 4 changes (docker-compose.yml, nginx.conf,
api.ts, App.tsx, SystemPanel.tsx) are replaced and the old copy is saved next to
them as <name>.bak. Files you edited that step 4 does not own are left alone.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Files from earlier steps that step 4 replaces (a .bak copy is saved first).
MANAGED = {
    "docker-compose.yml",
    "frontend/nginx.conf",
    "frontend/src/api.ts",
    "frontend/src/App.tsx",
    "frontend/src/components/SystemPanel.tsx",
}

FILES: dict[str, str] = {}

# ---------------------------------------------------------------------------
# docker-compose (steps 1 to 3 + notification-db + notification-service)
# ---------------------------------------------------------------------------
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

  # ---------- user-service (Python) ----------
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

  # ---------- tweet-service (Node.js) ----------
  tweet-db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: tweets
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: tweets
    volumes:
      - tweet_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tweets -d tweets"]
      interval: 5s
      timeout: 5s
      retries: 10

  tweet-service:
    build: ./services/tweet-service
    restart: unless-stopped
    environment:
      SERVICE_NAME: tweet-service
      PORT: "8000"
      DATABASE_URL: postgresql://tweets:${DB_PASSWORD}@tweet-db:5432/tweets
      RABBITMQ_URL: amqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@rabbitmq:5672/
      JWT_SECRET: ${JWT_SECRET}
      USER_SERVICE_URL: http://user-service:8000
    depends_on:
      tweet-db:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
      user-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://127.0.0.1:8000/health').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 10s

  # ---------- like-service (Node.js) ----------
  like-db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: likes
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: likes
    volumes:
      - like_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U likes -d likes"]
      interval: 5s
      timeout: 5s
      retries: 10

  like-service:
    build: ./services/like-service
    restart: unless-stopped
    environment:
      SERVICE_NAME: like-service
      PORT: "8000"
      DATABASE_URL: postgresql://likes:${DB_PASSWORD}@like-db:5432/likes
      RABBITMQ_URL: amqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@rabbitmq:5672/
      JWT_SECRET: ${JWT_SECRET}
      TWEET_SERVICE_URL: http://tweet-service:8000
    depends_on:
      like-db:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
      tweet-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://127.0.0.1:8000/health').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 10s

  # ---------- notification-service (Node.js) ----------
  notification-db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: notifications
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: notifications
    volumes:
      - notification_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U notifications -d notifications"]
      interval: 5s
      timeout: 5s
      retries: 10

  notification-service:
    build: ./services/notification-service
    restart: unless-stopped
    environment:
      SERVICE_NAME: notification-service
      PORT: "8000"
      DATABASE_URL: postgresql://notifications:${DB_PASSWORD}@notification-db:5432/notifications
      RABBITMQ_URL: amqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@rabbitmq:5672/
      JWT_SECRET: ${JWT_SECRET}
    depends_on:
      notification-db:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://127.0.0.1:8000/health').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 10s

  # ---------- frontend ----------
  frontend:
    build: ./frontend
    restart: unless-stopped
    ports:
      - "8080:80"
    depends_on:
      - user-service
      - tweet-service
      - like-service
      - notification-service

volumes:
  user_db_data:
  tweet_db_data:
  like_db_data:
  notification_db_data:
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

    location /api/tweets {
        set $tweet_service http://tweet-service:8000;
        proxy_pass $tweet_service;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Request-ID $request_id;
    }

    location /api/likes {
        set $like_service http://like-service:8000;
        proxy_pass $like_service;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Request-ID $request_id;
    }

    location /api/notifications {
        set $notification_service http://notification-service:8000;
        proxy_pass $notification_service;
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

# ---------------------------------------------------------------------------
# notification-service (Node.js / Express)
# ---------------------------------------------------------------------------
FILES["services/notification-service/package.json"] = r'''{
  "name": "notification-service",
  "version": "0.1.0",
  "private": true,
  "main": "src/index.js",
  "scripts": {
    "start": "node src/index.js",
    "test": "node --test"
  },
  "engines": {
    "node": ">=20"
  },
  "dependencies": {
    "amqplib": "^0.10.4",
    "express": "^4.21.1",
    "jsonwebtoken": "^9.0.2",
    "pg": "^8.13.0"
  }
}
'''

FILES["services/notification-service/Dockerfile"] = r'''FROM node:20-alpine
ENV NODE_ENV=production
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY src ./src

USER node
EXPOSE 8000
CMD ["node", "src/index.js"]
'''

FILES["services/notification-service/.dockerignore"] = r'''node_modules
test
npm-debug.log
'''

FILES["services/notification-service/src/logger.js"] = r'''// One JSON object per line, same field names in every service (see docs/contracts.md).
function createLogger(service, requestId = '-') {
  function write(level, message, fields) {
    if (process.env.LOG_SILENT === '1') return;
    const entry = {
      timestamp: new Date().toISOString(),
      level,
      service,
      message,
      request_id: requestId,
      ...fields,
    };
    process.stdout.write(JSON.stringify(entry) + '\n');
  }

  return {
    info: (message, fields = {}) => write('INFO', message, fields),
    warn: (message, fields = {}) => write('WARNING', message, fields),
    error: (message, fields = {}) => write('ERROR', message, fields),
  };
}

module.exports = { createLogger };
'''

FILES["services/notification-service/src/reporter.js"] = r'''// Tells monitor-service about every request this service handles (for the live dashboard).
// Fire and forget: if MONITOR_URL is not set or monitor-service is down, nothing happens.
function reportMiddleware({ serviceName }) {
  const monitorUrl = process.env.MONITOR_URL || '';

  return (req, res, next) => {
    if (!monitorUrl) return next();
    const started = process.hrtime.bigint();
    res.on('finish', () => {
      const path = req.originalUrl.split('?')[0];
      if (path.endsWith('/health') || path.endsWith('/ready')) return;
      const record = {
        time: new Date().toISOString(),
        service: serviceName,
        caller: req.headers['x-caller'] || 'browser',
        method: req.method,
        path,
        status: res.statusCode,
        duration_ms: Math.round(Number(process.hrtime.bigint() - started) / 1e5) / 10,
        request_id: String(res.getHeader('x-request-id') || req.headers['x-request-id'] || '-'),
      };
      fetch(`${monitorUrl}/api/monitor/ingest/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(record),
        signal: AbortSignal.timeout(1000),
      }).catch(() => {});
    });
    return next();
  };
}

module.exports = { reportMiddleware };
'''

FILES["services/notification-service/src/db.js"] = r'''const { Pool } = require('pg');

function createDb(connectionString, logger) {
  const pool = new Pool({ connectionString, max: 5 });
  pool.on('error', (err) => logger.warn(`database connection error: ${err.message}`));
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  return {
    // Create the table. Retries because the database may still be starting.
    async init() {
      for (let attempt = 1; attempt <= 30; attempt++) {
        try {
          await pool.query(`
            CREATE TABLE IF NOT EXISTS notifications (
              id SERIAL PRIMARY KEY,
              user_id INTEGER NOT NULL,
              type VARCHAR(30) NOT NULL,
              message VARCHAR(200) NOT NULL,
              tweet_id INTEGER,
              event_id VARCHAR(64) NOT NULL UNIQUE,
              is_read BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )`);
          await pool.query('CREATE INDEX IF NOT EXISTS notifications_user_idx ON notifications (user_id, id DESC)');
          logger.info('database ready');
          return;
        } catch (err) {
          logger.warn(`database not ready (${err.message}), retry ${attempt}/30`);
          await sleep(2000);
        }
      }
      throw new Error('database never became ready');
    },

    async ping() {
      await pool.query('SELECT 1');
    },

    // Returns true if saved, false if this event had already been handled (same event id).
    async addNotification({ userId, type, message, tweetId, eventId }) {
      const { rows } = await pool.query(
        `INSERT INTO notifications (user_id, type, message, tweet_id, event_id)
         VALUES ($1, $2, $3, $4, $5) ON CONFLICT (event_id) DO NOTHING RETURNING id`,
        [userId, type, message, tweetId, eventId]
      );
      return rows.length > 0;
    },

    async listForUser(userId, limit) {
      const { rows } = await pool.query(
        `SELECT id, type, message, tweet_id, is_read, created_at
         FROM notifications WHERE user_id = $1 ORDER BY id DESC LIMIT $2`,
        [userId, limit]
      );
      return rows;
    },

    async countUnread(userId) {
      const { rows } = await pool.query(
        'SELECT COUNT(*)::int AS count FROM notifications WHERE user_id = $1 AND NOT is_read',
        [userId]
      );
      return rows[0].count;
    },

    async markAllRead(userId) {
      await pool.query('UPDATE notifications SET is_read = TRUE WHERE user_id = $1 AND NOT is_read', [userId]);
    },

    async close() {
      await pool.end();
    },
  };
}

module.exports = { createDb };
'''

FILES["services/notification-service/src/events.js"] = r'''const crypto = require('crypto');
const amqp = require('amqplib');
const { createLogger } = require('./logger');

const EXCHANGE = 'minitweet';

function withTimeout(promise, ms, what) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${what} timed out`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function createEvents({ url, serviceName }) {
  async function connect() {
    const connection = await withTimeout(amqp.connect(url), 3000, 'RabbitMQ connection');
    connection.on('error', () => {}); // errors surface where we use the connection; do not crash
    return connection;
  }

  // Best effort: if RabbitMQ is down we log a warning and carry on. Never throws.
  async function publish(type, data, requestId) {
    if (!url) return;
    const log = createLogger(serviceName, requestId);
    const message = {
      id: crypto.randomUUID(),
      type,
      time: new Date().toISOString(),
      source: serviceName,
      data,
    };
    try {
      const connection = await connect();
      try {
        const channel = await connection.createChannel();
        await channel.assertExchange(EXCHANGE, 'topic', { durable: true });
        channel.publish(EXCHANGE, type, Buffer.from(JSON.stringify(message)), {
          persistent: true,
          contentType: 'application/json',
        });
        await channel.close();
      } finally {
        await connection.close();
      }
      log.info(`event published: ${type}`, { event_id: message.id });
    } catch (err) {
      log.warn(`could not publish ${type}: ${err.message}`);
    }
  }

  async function check() {
    if (!url) return 'not configured';
    try {
      const connection = await connect();
      await connection.close();
      return 'ok';
    } catch {
      return 'unavailable';
    }
  }

  return { publish, check };
}

module.exports = { createEvents };
'''

FILES["services/notification-service/src/consumer.js"] = r'''const amqp = require('amqplib');
const { createLogger } = require('./logger');

const EXCHANGE = 'minitweet';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Listens to events and hands each one to onEvent. Reconnects by itself if RabbitMQ goes away.
function startConsumer({ url, serviceName, queue, bindings, onEvent }) {
  const log = createLogger(serviceName);
  let stopped = false;
  let currentConnection = null;

  async function listen(connection) {
    const channel = await connection.createChannel();
    await channel.assertExchange(EXCHANGE, 'topic', { durable: true });
    await channel.assertQueue(queue, { durable: true });
    for (const key of bindings) await channel.bindQueue(queue, EXCHANGE, key);
    await channel.prefetch(10);
    await channel.consume(queue, async (msg) => {
      if (msg === null) return;

      let event;
      try {
        event = JSON.parse(msg.content.toString());
        if (!event || typeof event !== 'object') throw new Error('not an object');
      } catch {
        log.error('dropping a message that is not a valid event');
        channel.ack(msg);
        return;
      }

      try {
        await onEvent(event);
        channel.ack(msg);
      } catch (err) {
        // Try once more. After that give up on this message so it cannot block the queue.
        const retry = !msg.fields.redelivered;
        log.error(`failed to handle ${event.type}: ${err.message}`, { event_id: event.id, will_retry: retry });
        channel.nack(msg, false, retry);
      }
    });
    log.info(`listening for events on queue ${queue}`, { bindings: bindings.join(',') });
  }

  async function loop() {
    while (!stopped) {
      try {
        const connection = await amqp.connect(url);
        currentConnection = connection;
        await new Promise((resolve) => {
          connection.on('error', (err) => log.warn(`RabbitMQ error: ${err.message}`));
          connection.on('close', resolve);
          listen(connection).catch((err) => {
            log.error(`could not start listening: ${err.message}`);
            connection.close().catch(() => {});
          });
        });
        if (!stopped) log.warn('RabbitMQ connection lost, reconnecting in 5s');
      } catch (err) {
        log.warn(`cannot reach RabbitMQ (${err.message}), retrying in 5s`);
      }
      if (!stopped) await sleep(5000);
    }
  }

  if (url) loop();

  return {
    async stop() {
      stopped = true;
      if (currentConnection) await currentConnection.close().catch(() => {});
    },
  };
}

module.exports = { startConsumer };
'''

FILES["services/notification-service/src/handlers.js"] = r'''// What notification-service does when an event arrives.
// Each notification remembers the id of the event that made it, so if the same event is
// delivered twice the second one is ignored (no double notifications).
function createEventHandler({ db, logger }) {
  return async function handle(event) {
    const data = event.data || {};

    if (event.type === 'user.registered') {
      if (!Number.isInteger(data.user_id)) throw new Error('user.registered without a user_id');
      await db.addNotification({
        userId: data.user_id,
        type: 'welcome',
        message: `Welcome to MiniTweet, @${data.username}!`.slice(0, 200),
        tweetId: null,
        eventId: event.id,
      });
      logger.info(`welcome notification for user ${data.user_id}`, { event_id: event.id });
      return;
    }

    if (event.type === 'tweet.liked') {
      if (!Number.isInteger(data.tweet_author_id) || !Number.isInteger(data.liked_by_id)) {
        throw new Error('tweet.liked without tweet_author_id or liked_by_id');
      }
      // Nobody needs a notification about liking their own tweet.
      if (data.tweet_author_id === data.liked_by_id) return;
      await db.addNotification({
        userId: data.tweet_author_id,
        type: 'like',
        message: `@${data.liked_by_username} liked your tweet`.slice(0, 200),
        tweetId: Number.isInteger(data.tweet_id) ? data.tweet_id : null,
        eventId: event.id,
      });
      logger.info(`like notification for user ${data.tweet_author_id}`, { event_id: event.id });
    }
    // Any other event is not for us: ignore it.
  };
}

module.exports = { createEventHandler };
'''

FILES["services/notification-service/src/app.js"] = r'''const crypto = require('crypto');
const express = require('express');
const jwt = require('jsonwebtoken');
const { createLogger } = require('./logger');

// The app is built from its dependencies so the tests can plug in fakes.
function createApp({ config, db, events }) {
  const app = express();
  const logger = createLogger(config.serviceName);
  app.disable('x-powered-by');

  // Request id + one JSON log line per request (health checks are left out).
  app.use((req, res, next) => {
    req.id = req.headers['x-request-id'] || crypto.randomBytes(6).toString('hex');
    req.log = createLogger(config.serviceName, req.id);
    res.setHeader('X-Request-ID', req.id);
    const started = process.hrtime.bigint();
    res.on('finish', () => {
      const path = req.originalUrl.split('?')[0];
      if (path.endsWith('/health') || path.endsWith('/ready')) return;
      req.log.info(`${req.method} ${path} ${res.statusCode}`, {
        method: req.method,
        path,
        status: res.statusCode,
        duration_ms: Math.round(Number(process.hrtime.bigint() - started) / 1e5) / 10,
        caller: req.headers['x-caller'] || 'browser',
      });
    });
    next();
  });

  app.use(express.json({ limit: '10kb' }));

  const wrap = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);

  // The token is checked here with the shared secret. No call to user-service.
  function requireAuth(req, res, next) {
    const header = req.headers.authorization || '';
    if (!header.startsWith('Bearer ')) return res.status(401).json({ detail: 'missing token' });
    try {
      const claims = jwt.verify(header.slice(7), config.jwtSecret, { algorithms: ['HS256'] });
      req.user = { id: Number(claims.sub), username: claims.username };
      return next();
    } catch {
      return res.status(401).json({ detail: 'invalid or expired token' });
    }
  }

  app.get(['/health', '/api/notifications/health'], (req, res) => {
    res.json({ status: 'ok', service: config.serviceName });
  });

  // Ready means "I can do my job". RabbitMQ is reported but optional for the REST side.
  app.get(['/ready', '/api/notifications/ready'], wrap(async (req, res) => {
    let database = 'ok';
    try {
      await db.ping();
    } catch {
      database = 'unavailable';
    }
    const rabbitmq = await events.check();
    res.status(database === 'ok' ? 200 : 503).json({
      status: database === 'ok' ? 'ready' : 'not ready',
      checks: { database, rabbitmq },
    });
  }));

  // My notifications (newest first) and how many I have not read yet.
  app.get('/api/notifications', requireAuth, wrap(async (req, res) => {
    const [notifications, unread] = await Promise.all([
      db.listForUser(req.user.id, 50),
      db.countUnread(req.user.id),
    ]);
    res.json({ unread, notifications });
  }));

  app.post('/api/notifications/read', requireAuth, wrap(async (req, res) => {
    await db.markAllRead(req.user.id);
    res.json({ unread: 0 });
  }));

  app.use((req, res) => res.status(404).json({ detail: 'not found' }));

  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    if (err.type === 'entity.parse.failed') return res.status(400).json({ detail: 'invalid JSON' });
    (req.log || logger).error('unhandled error', { error: err.message });
    return res.status(500).json({ detail: 'internal error' });
  });

  return app;
}

module.exports = { createApp };
'''

FILES["services/notification-service/src/index.js"] = r'''const express = require('express');

const { createApp } = require('./app');
const { startConsumer } = require('./consumer');
const { createDb } = require('./db');
const { createEvents } = require('./events');
const { createEventHandler } = require('./handlers');
const { createLogger } = require('./logger');
const { reportMiddleware } = require('./reporter');

function required(name) {
  if (!process.env[name]) throw new Error(`missing environment variable ${name}`);
  return process.env[name];
}

const config = {
  serviceName: process.env.SERVICE_NAME || 'notification-service',
  port: Number(process.env.PORT || 8000),
  databaseUrl: required('DATABASE_URL'),
  rabbitmqUrl: process.env.RABBITMQ_URL || '',
  jwtSecret: required('JWT_SECRET'),
};

async function main() {
  const logger = createLogger(config.serviceName);
  const db = createDb(config.databaseUrl, logger);
  await db.init();

  const events = createEvents({ url: config.rabbitmqUrl, serviceName: config.serviceName });
  const app = createApp({ config, db, events });

  // Listen for the events that should create notifications.
  const consumer = startConsumer({
    url: config.rabbitmqUrl,
    serviceName: config.serviceName,
    queue: 'notification-service.events',
    bindings: ['user.registered', 'tweet.liked'],
    onEvent: createEventHandler({ db, logger }),
  });

  // Tell monitor-service about every request (for the dashboard).
  const root = express();
  root.use(reportMiddleware({ serviceName: config.serviceName }));
  root.use(app);
  const server = root.listen(config.port, () => logger.info(`listening on port ${config.port}`));

  // Stop cleanly when Docker or Kubernetes asks us to.
  const shutdown = async () => {
    logger.info('shutting down');
    await consumer.stop();
    server.close(async () => {
      await db.close();
      process.exit(0);
    });
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
'''

FILES["services/notification-service/test/app.test.js"] = r'''process.env.LOG_SILENT = '1';

const test = require('node:test');
const assert = require('node:assert/strict');
const jwt = require('jsonwebtoken');
const { createApp } = require('../src/app');
const { createEventHandler } = require('../src/handlers');
const { createLogger } = require('../src/logger');

const SECRET = 'test-secret';
const adel = { id: 1, username: 'adel' };
const sara = { id: 2, username: 'sara' };

function token(user, secret = SECRET) {
  return jwt.sign({ sub: String(user.id), username: user.username }, secret, {
    algorithm: 'HS256',
    expiresIn: '1h',
  });
}

function fakeDb() {
  const rows = [];
  let nextId = 1;
  return {
    rows,
    async addNotification({ userId, type, message, tweetId, eventId }) {
      if (rows.some((r) => r.event_id === eventId)) return false;
      rows.push({
        id: nextId++, user_id: userId, type, message, tweet_id: tweetId, event_id: eventId,
        is_read: false, created_at: new Date().toISOString(),
      });
      return true;
    },
    async listForUser(userId, limit) {
      return rows
        .filter((r) => r.user_id === userId)
        .reverse()
        .slice(0, limit)
        .map(({ id, type, message, tweet_id, is_read, created_at }) => ({ id, type, message, tweet_id, is_read, created_at }));
    },
    async countUnread(userId) {
      return rows.filter((r) => r.user_id === userId && !r.is_read).length;
    },
    async markAllRead(userId) {
      rows.filter((r) => r.user_id === userId).forEach((r) => { r.is_read = true; });
    },
    async ping() {},
  };
}

async function start(db = fakeDb()) {
  const deps = {
    config: { serviceName: 'notification-service', jwtSecret: SECRET },
    db,
    events: { async check() { return 'ok'; } },
  };
  const server = await new Promise((resolve) => {
    const s = createApp(deps).listen(0, () => resolve(s));
  });
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    db,
    close: () =>
      new Promise((resolve) => {
        server.close(resolve);
        server.closeAllConnections();
      }),
  };
}

async function withApp(fn, db) {
  const app = await start(db);
  try {
    await fn(app);
  } finally {
    await app.close();
  }
}

function call(app, method, path, { as, secret } = {}) {
  const headers = {};
  if (as) headers.Authorization = `Bearer ${token(as, secret)}`;
  return fetch(`${app.url}${path}`, { method, headers });
}

test('notifications need a token', () =>
  withApp(async (app) => {
    assert.equal((await call(app, 'GET', '/api/notifications')).status, 401);
    assert.equal((await call(app, 'POST', '/api/notifications/read')).status, 401);
    assert.equal((await call(app, 'GET', '/api/notifications', { as: adel, secret: 'other-secret' })).status, 401);
  }));

test('you only see your own notifications, newest first, with the unread count', () =>
  withApp(async (app) => {
    await app.db.addNotification({ userId: 1, type: 'welcome', message: 'Welcome', tweetId: null, eventId: 'a' });
    await app.db.addNotification({ userId: 2, type: 'welcome', message: 'Welcome sara', tweetId: null, eventId: 'b' });
    await app.db.addNotification({ userId: 1, type: 'like', message: 'sara liked', tweetId: 5, eventId: 'c' });

    const body = await (await call(app, 'GET', '/api/notifications', { as: adel })).json();
    assert.equal(body.unread, 2);
    assert.deepEqual(body.notifications.map((n) => n.message), ['sara liked', 'Welcome']);

    const other = await (await call(app, 'GET', '/api/notifications', { as: sara })).json();
    assert.equal(other.unread, 1);
    assert.equal(other.notifications.length, 1);
  }));

test('marking as read clears only my unread count', () =>
  withApp(async (app) => {
    await app.db.addNotification({ userId: 1, type: 'welcome', message: 'Welcome', tweetId: null, eventId: 'a' });
    await app.db.addNotification({ userId: 2, type: 'welcome', message: 'Welcome sara', tweetId: null, eventId: 'b' });

    const res = await call(app, 'POST', '/api/notifications/read', { as: adel });
    assert.deepEqual(await res.json(), { unread: 0 });

    const mine = await (await call(app, 'GET', '/api/notifications', { as: adel })).json();
    assert.equal(mine.unread, 0);
    assert.equal(mine.notifications[0].is_read, true);
    const others = await (await call(app, 'GET', '/api/notifications', { as: sara })).json();
    assert.equal(others.unread, 1);
  }));

test('health and ready answer', () =>
  withApp(async (app) => {
    assert.equal((await (await call(app, 'GET', '/health')).json()).status, 'ok');
    const ready = await call(app, 'GET', '/ready');
    assert.equal(ready.status, 200);
    assert.equal((await ready.json()).checks.database, 'ok');
  }));

// ---- what happens when an event arrives ----
const logger = createLogger('notification-service');

test('user.registered creates a welcome notification', async () => {
  const db = fakeDb();
  await createEventHandler({ db, logger })({ id: 'e1', type: 'user.registered', data: { user_id: 7, username: 'omar' } });
  assert.equal(db.rows.length, 1);
  assert.equal(db.rows[0].user_id, 7);
  assert.equal(db.rows[0].type, 'welcome');
  assert.equal(db.rows[0].message, 'Welcome to MiniTweet, @omar!');
});

test('tweet.liked notifies the tweet author', async () => {
  const db = fakeDb();
  await createEventHandler({ db, logger })({
    id: 'e2',
    type: 'tweet.liked',
    data: { tweet_id: 5, tweet_author_id: 2, liked_by_id: 1, liked_by_username: 'adel' },
  });
  assert.equal(db.rows.length, 1);
  assert.equal(db.rows[0].user_id, 2);
  assert.equal(db.rows[0].type, 'like');
  assert.equal(db.rows[0].message, '@adel liked your tweet');
  assert.equal(db.rows[0].tweet_id, 5);
});

test('liking your own tweet creates no notification', async () => {
  const db = fakeDb();
  await createEventHandler({ db, logger })({
    id: 'e3',
    type: 'tweet.liked',
    data: { tweet_id: 5, tweet_author_id: 1, liked_by_id: 1, liked_by_username: 'adel' },
  });
  assert.equal(db.rows.length, 0);
});

test('the same event delivered twice creates one notification', async () => {
  const db = fakeDb();
  const handle = createEventHandler({ db, logger });
  const event = { id: 'same-id', type: 'user.registered', data: { user_id: 7, username: 'omar' } };
  await handle(event);
  await handle(event);
  assert.equal(db.rows.length, 1);
});

test('events with missing data are rejected, unknown events are ignored', async () => {
  const db = fakeDb();
  const handle = createEventHandler({ db, logger });
  await assert.rejects(() => handle({ id: 'e4', type: 'user.registered', data: {} }));
  await assert.rejects(() => handle({ id: 'e5', type: 'tweet.liked', data: { tweet_id: 5 } }));
  await handle({ id: 'e6', type: 'tweet.created', data: { tweet_id: 5 } });
  assert.equal(db.rows.length, 0);
});
'''

FILES["services/notification-service/test/reporter.test.js"] = r'''const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { EventEmitter } = require('node:events');
const { reportMiddleware } = require('../src/reporter');

// A tiny stand-in for monitor-service that remembers what it receives.
async function startFakeMonitor() {
  const received = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      received.push({ url: req.url, record: JSON.parse(body) });
      res.end('ok');
    });
  });
  await new Promise((resolve) => server.listen(0, resolve));
  return {
    received,
    url: `http://127.0.0.1:${server.address().port}`,
    close: () => new Promise((resolve) => { server.close(resolve); server.closeAllConnections(); }),
  };
}

async function waitFor(condition, ms = 1500) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (condition()) return true;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  return false;
}

function fakeResponse(status = 200, requestId = 'abc123') {
  const res = new EventEmitter();
  res.statusCode = status;
  res.getHeader = (name) => (name === 'x-request-id' ? requestId : undefined);
  return res;
}

test('a finished request is reported to monitor-service', async () => {
  const monitor = await startFakeMonitor();
  process.env.MONITOR_URL = monitor.url;
  try {
    const middleware = reportMiddleware({ serviceName: 'tweet-service' });
    const req = { originalUrl: '/api/tweets?limit=5', method: 'GET', headers: { 'x-caller': 'like-service' } };
    const res = fakeResponse(200);
    let nextCalled = false;
    middleware(req, res, () => { nextCalled = true; });
    assert.equal(nextCalled, true);
    res.emit('finish');

    assert.equal(await waitFor(() => monitor.received.length === 1), true);
    assert.equal(monitor.received[0].url, '/api/monitor/ingest/request');
    const record = monitor.received[0].record;
    assert.equal(record.service, 'tweet-service');
    assert.equal(record.caller, 'like-service');
    assert.equal(record.method, 'GET');
    assert.equal(record.path, '/api/tweets');
    assert.equal(record.status, 200);
    assert.equal(record.request_id, 'abc123');
    assert.equal(typeof record.duration_ms, 'number');
  } finally {
    delete process.env.MONITOR_URL;
    await monitor.close();
  }
});

test('requests from the browser are reported with caller "browser"', async () => {
  const monitor = await startFakeMonitor();
  process.env.MONITOR_URL = monitor.url;
  try {
    const middleware = reportMiddleware({ serviceName: 'tweet-service' });
    const res = fakeResponse(201);
    middleware({ originalUrl: '/api/tweets', method: 'POST', headers: {} }, res, () => {});
    res.emit('finish');
    assert.equal(await waitFor(() => monitor.received.length === 1), true);
    assert.equal(monitor.received[0].record.caller, 'browser');
  } finally {
    delete process.env.MONITOR_URL;
    await monitor.close();
  }
});

test('health and ready checks are not reported', async () => {
  const monitor = await startFakeMonitor();
  process.env.MONITOR_URL = monitor.url;
  try {
    const middleware = reportMiddleware({ serviceName: 'tweet-service' });
    for (const path of ['/health', '/ready', '/api/tweets/health']) {
      const res = fakeResponse(200);
      middleware({ originalUrl: path, method: 'GET', headers: {} }, res, () => {});
      res.emit('finish');
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
    assert.equal(monitor.received.length, 0);
  } finally {
    delete process.env.MONITOR_URL;
    await monitor.close();
  }
});

test('without MONITOR_URL nothing is sent and the request carries on', () => {
  delete process.env.MONITOR_URL;
  const middleware = reportMiddleware({ serviceName: 'tweet-service' });
  const res = fakeResponse(200);
  let nextCalled = false;
  middleware({ originalUrl: '/api/tweets', method: 'GET', headers: {} }, res, () => { nextCalled = true; });
  assert.equal(nextCalled, true);
  assert.equal(res.listenerCount('finish'), 0);
});

test('if monitor-service is down the request is not affected', async () => {
  process.env.MONITOR_URL = 'http://127.0.0.1:9';
  try {
    const middleware = reportMiddleware({ serviceName: 'tweet-service' });
    const res = fakeResponse(200);
    middleware({ originalUrl: '/api/tweets', method: 'GET', headers: {} }, res, () => {});
    res.emit('finish');
    await new Promise((resolve) => setTimeout(resolve, 200)); // no crash, no unhandled rejection
  } finally {
    delete process.env.MONITOR_URL;
  }
});
'''

# ---------------------------------------------------------------------------
# frontend changes
# ---------------------------------------------------------------------------
FILES["frontend/src/time.ts"] = r'''export function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}
'''

FILES["frontend/src/api.ts"] = r'''export interface User {
  id: number;
  username: string;
  created_at?: string;
}

export interface Tweet {
  id: number;
  user_id: number;
  username: string;
  content: string;
  created_at: string;
}

export interface LikeInfo {
  count: number;
  liked_by_me: boolean;
}

export interface LikeResult {
  tweet_id: number;
  liked: boolean;
  count: number;
}

export interface AppNotification {
  id: number;
  type: string;
  message: string;
  tweet_id: number | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationList {
  unread: number;
  notifications: AppNotification[];
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

// ---- users ----
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

// ---- tweets ----
export function listTweets(): Promise<Tweet[]> {
  return request<Tweet[]>("/tweets?limit=30");
}

export function createTweet(content: string): Promise<Tweet> {
  return request<Tweet>("/tweets", { method: "POST", body: JSON.stringify({ content }) });
}

export async function deleteTweet(id: number): Promise<void> {
  await request<unknown>(`/tweets/${id}`, { method: "DELETE" });
}

// ---- likes ----
export function getLikes(ids: number[]): Promise<Record<string, LikeInfo>> {
  return request<Record<string, LikeInfo>>(`/likes?tweet_ids=${ids.join(",")}`);
}

export function likeTweet(id: number): Promise<LikeResult> {
  return request<LikeResult>("/likes", { method: "POST", body: JSON.stringify({ tweet_id: id }) });
}

export function unlikeTweet(id: number): Promise<LikeResult> {
  return request<LikeResult>(`/likes/${id}`, { method: "DELETE" });
}

// ---- notifications ----
export function getNotifications(): Promise<NotificationList> {
  return request<NotificationList>("/notifications");
}

export function markNotificationsRead(): Promise<{ unread: number }> {
  return request<{ unread: number }>("/notifications/read", { method: "POST" });
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

FILES["frontend/src/components/Notifications.tsx"] = r'''import type { AppNotification } from "../api";
import { timeAgo } from "../time";

interface Props {
  items: AppNotification[] | null;
  unread: number;
  onMarkRead: () => void;
}

export default function Notifications({ items, unread, onMarkRead }: Props) {
  if (items === null) {
    return (
      <div className="space-y-3">
        <div className="h-16 animate-pulse rounded-2xl bg-black/5 dark:bg-white/10" />
        <div className="h-16 animate-pulse rounded-2xl bg-black/5 dark:bg-white/10" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm opacity-70">{unread > 0 ? `${unread} unread` : "You are all caught up"}</p>
        {unread > 0 && (
          <button
            onClick={onMarkRead}
            className="rounded-full border border-black/10 px-4 py-1.5 text-xs font-semibold transition hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          >
            Mark all as read
          </button>
        )}
      </div>

      {items.length === 0 && (
        <div className="rounded-2xl border border-dashed border-black/10 p-8 text-center text-sm opacity-70 dark:border-white/20">
          No notifications yet. When someone likes your tweet, you will see it here.
        </div>
      )}

      {items.map((item) => (
        <div
          key={item.id}
          className={`flex items-start gap-3 rounded-2xl border p-4 shadow-sm ${
            item.is_read
              ? "border-black/5 bg-card dark:border-white/10 dark:bg-card-dark"
              : "border-brand/40 bg-brand/5 dark:bg-brand/10"
          }`}
        >
          <span className="text-xl">{item.type === "like" ? "♥" : "🎉"}</span>
          <div className="min-w-0 flex-1">
            <p className="break-words text-sm">{item.message}</p>
            <p className="mt-0.5 text-xs opacity-60">{timeAgo(item.created_at)}</p>
          </div>
          {!item.is_read && <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-brand" />}
        </div>
      ))}
    </div>
  );
}
'''

FILES["frontend/src/components/MainArea.tsx"] = r'''import { useCallback, useEffect, useState } from "react";

import { getNotifications, markNotificationsRead } from "../api";
import type { AppNotification, User } from "../api";
import Feed from "./Feed";
import Notifications from "./Notifications";

export default function MainArea({ user }: { user: User }) {
  const [tab, setTab] = useState<"feed" | "notifications">("feed");
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [unread, setUnread] = useState(0);

  const load = useCallback(async () => {
    try {
      const data = await getNotifications();
      setItems(data.notifications);
      setUnread(data.unread);
    } catch {
      // Notifications are optional: if notification-service is down the feed still works.
    }
  }, []);

  // Check for new notifications every 5 seconds, so the badge updates on every tab.
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load]);

  async function markRead() {
    try {
      const result = await markNotificationsRead();
      setUnread(result.unread);
      await load();
    } catch {
      // ignore: the next refresh will show the real state
    }
  }

  const tabClass = (active: boolean) =>
    `flex-1 rounded-lg py-2 text-sm font-semibold transition ${
      active ? "bg-brand text-white shadow" : "opacity-70 hover:opacity-100"
    }`;

  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-xl bg-black/5 p-1 dark:bg-white/10">
        <button className={tabClass(tab === "feed")} onClick={() => setTab("feed")}>
          Feed
        </button>
        <button className={tabClass(tab === "notifications")} onClick={() => setTab("notifications")}>
          Notifications
          {unread > 0 && (
            <span className="ml-2 rounded-full bg-accent px-2 py-0.5 text-xs font-bold text-white">{unread}</span>
          )}
        </button>
      </div>

      {tab === "feed" ? (
        <Feed user={user} />
      ) : (
        <Notifications items={items} unread={unread} onMarkRead={() => void markRead()} />
      )}
    </div>
  );
}
'''

FILES["frontend/src/components/SystemPanel.tsx"] = r'''const SERVICES = [
  { name: "user-service", tech: "Python", state: "built" },
  { name: "tweet-service", tech: "Node.js", state: "built" },
  { name: "like-service", tech: "Node.js", state: "built" },
  { name: "notification-service", tech: "Node.js", state: "built" },
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
import MainArea from "./components/MainArea";
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
            <div className="space-y-4">
              <Profile user={user} onLogout={logout} />
              <MainArea user={user} />
            </div>
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


def main() -> int:
    parser = argparse.ArgumentParser(description="MiniTweet v2 - step 4 setup")
    parser.add_argument("--force", action="store_true", help="also overwrite files you edited (.bak saved)")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list files left alone")
    args = parser.parse_args()

    root = Path.cwd()
    if not (root / "services" / "like-service" / "src" / "app.js").exists() or not (root / "docker-compose.yml").exists():
        print("Step 3 is not in this folder. Run this script inside the folder where step 3 works.")
        return 1

    counts = {"created": 0, "updated": 0, "kept": 0}
    print(f"MiniTweet step 4 in: {root}" + ("  [dry run]" if args.dry_run else ""))

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
        print("\nNext:\n  docker compose up --build\n  then open http://localhost:8080")
    return 0


if __name__ == "__main__":
    sys.exit(main())
