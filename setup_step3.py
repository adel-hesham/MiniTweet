#!/usr/bin/env python3
"""
MiniTweet v2 - Step 3: like-service (Node.js) + like buttons in the feed.

Run it in the same folder where step 2 already works:

    python setup_step3.py              # add everything for step 3
    python setup_step3.py --dry-run    # show what would happen, change nothing
    python setup_step3.py -v           # also list files that were left alone
    python setup_step3.py --force      # also overwrite files you edited (a .bak copy is saved)

Safe to run again. Shared files that step 3 changes (docker-compose.yml, nginx.conf,
api.ts, Feed.tsx, SystemPanel.tsx) are replaced and the old copy is saved next to
them as <name>.bak. Files you edited that step 3 does not own are left alone.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Files from earlier steps that step 3 replaces (a .bak copy is saved first).
MANAGED = {
    "docker-compose.yml",
    "frontend/nginx.conf",
    "frontend/src/api.ts",
    "frontend/src/components/Feed.tsx",
    "frontend/src/components/SystemPanel.tsx",
}

FILES: dict[str, str] = {}

# ---------------------------------------------------------------------------
# docker-compose (steps 1 and 2 + like-db + like-service)
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

volumes:
  user_db_data:
  tweet_db_data:
  like_db_data:
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

    location / {
        try_files $uri /index.html;
    }
}
'''

# ---------------------------------------------------------------------------
# like-service (Node.js / Express)
# ---------------------------------------------------------------------------
FILES["services/like-service/package.json"] = r'''{
  "name": "like-service",
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

FILES["services/like-service/Dockerfile"] = r'''FROM node:20-alpine
ENV NODE_ENV=production
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY src ./src

USER node
EXPOSE 8000
CMD ["node", "src/index.js"]
'''

FILES["services/like-service/.dockerignore"] = r'''node_modules
test
npm-debug.log
'''

FILES["services/like-service/src/logger.js"] = r'''// One JSON object per line, same field names in every service (see docs/contracts.md).
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

FILES["services/like-service/src/db.js"] = r'''const { Pool } = require('pg');

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
            CREATE TABLE IF NOT EXISTS likes (
              id SERIAL PRIMARY KEY,
              tweet_id INTEGER NOT NULL,
              user_id INTEGER NOT NULL,
              username VARCHAR(20) NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              UNIQUE (tweet_id, user_id)
            )`);
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

    // Returns true if the like is new, false if the user had already liked this tweet.
    async addLike({ tweetId, userId, username }) {
      const { rows } = await pool.query(
        `INSERT INTO likes (tweet_id, user_id, username) VALUES ($1, $2, $3)
         ON CONFLICT (tweet_id, user_id) DO NOTHING RETURNING id`,
        [tweetId, userId, username]
      );
      return rows.length > 0;
    },

    async removeLike(tweetId, userId) {
      await pool.query('DELETE FROM likes WHERE tweet_id = $1 AND user_id = $2', [tweetId, userId]);
    },

    async countLikes(tweetId) {
      const { rows } = await pool.query('SELECT COUNT(*)::int AS count FROM likes WHERE tweet_id = $1', [tweetId]);
      return rows[0].count;
    },

    // { "5": { count: 2, liked_by_me: true }, ... } with an entry for every id asked for.
    async likeSummary(tweetIds, userId) {
      const { rows } = await pool.query(
        `SELECT tweet_id, COUNT(*)::int AS count, BOOL_OR(user_id = $2) AS liked_by_me
         FROM likes WHERE tweet_id = ANY($1::int[]) GROUP BY tweet_id`,
        [tweetIds, userId]
      );
      const summary = {};
      for (const id of tweetIds) summary[id] = { count: 0, liked_by_me: false };
      for (const row of rows) summary[row.tweet_id] = { count: row.count, liked_by_me: row.liked_by_me };
      return summary;
    },

    async deleteLikesForTweet(tweetId) {
      const result = await pool.query('DELETE FROM likes WHERE tweet_id = $1', [tweetId]);
      return result.rowCount;
    },

    async close() {
      await pool.end();
    },
  };
}

module.exports = { createDb };
'''

FILES["services/like-service/src/events.js"] = r'''const crypto = require('crypto');
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

FILES["services/like-service/src/consumer.js"] = r'''const amqp = require('amqplib');
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

FILES["services/like-service/src/handlers.js"] = r'''// What like-service does when an event arrives.
function createEventHandler({ db, logger }) {
  return async function handle(event) {
    if (event.type === 'tweet.deleted') {
      const tweetId = event.data && event.data.tweet_id;
      if (!Number.isInteger(tweetId)) throw new Error('tweet.deleted without a tweet_id');
      const removed = await db.deleteLikesForTweet(tweetId);
      logger.info(`removed ${removed} like(s) of deleted tweet ${tweetId}`, { event_id: event.id });
    }
    // Any other event is not for us: ignore it.
  };
}

module.exports = { createEventHandler };
'''

FILES["services/like-service/src/tweetClient.js"] = r'''// Asks tweet-service "what is tweet N?" over REST.
// Returns the tweet, or null if it does not exist. Throws if tweet-service cannot be reached.
function createTweetClient({ baseUrl, serviceName }) {
  return async function getTweet(id, requestId) {
    let lastError;
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const response = await fetch(`${baseUrl}/api/tweets/${id}`, {
          headers: { 'X-Caller': serviceName, 'X-Request-ID': requestId },
          signal: AbortSignal.timeout(3000),
        });
        if (response.status === 404) return null;
        if (!response.ok) throw new Error(`tweet-service answered ${response.status}`);
        return await response.json();
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError;
  };
}

module.exports = { createTweetClient };
'''

FILES["services/like-service/src/app.js"] = r'''const crypto = require('crypto');
const express = require('express');
const jwt = require('jsonwebtoken');
const { createLogger } = require('./logger');

// The app is built from its dependencies so the tests can plug in fakes.
function createApp({ config, db, events, getTweet }) {
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

  app.get(['/health', '/api/likes/health'], (req, res) => {
    res.json({ status: 'ok', service: config.serviceName });
  });

  // Ready means "I can do my job". RabbitMQ is reported but optional,
  // because publishing events is best effort.
  app.get(['/ready', '/api/likes/ready'], wrap(async (req, res) => {
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

  // Like counts for several tweets at once: GET /api/likes?tweet_ids=1,2,3
  app.get('/api/likes', requireAuth, wrap(async (req, res) => {
    const text = String(req.query.tweet_ids || '');
    const ids = text === '' ? [] : text.split(',').map((part) => (/^\d+$/.test(part.trim()) ? Number(part) : NaN));
    if (ids.some(Number.isNaN) || ids.length > 50) {
      return res.status(422).json({ detail: 'tweet_ids must be up to 50 numbers separated by commas' });
    }
    return res.json(ids.length === 0 ? {} : await db.likeSummary(ids, req.user.id));
  }));

  app.post('/api/likes', requireAuth, wrap(async (req, res) => {
    const tweetId = req.body?.tweet_id;
    if (!Number.isInteger(tweetId) || tweetId < 1) {
      return res.status(422).json({ detail: 'tweet_id must be a positive number' });
    }

    // REST call to tweet-service: does this tweet exist, and who wrote it?
    let tweet;
    try {
      tweet = await getTweet(tweetId, req.id);
    } catch (err) {
      req.log.error('tweet-service call failed', { error: err.message });
      return res.status(503).json({ detail: 'tweet-service is unavailable, try again' });
    }
    if (!tweet) return res.status(404).json({ detail: 'tweet not found' });

    const created = await db.addLike({ tweetId, userId: req.user.id, username: req.user.username });
    const count = await db.countLikes(tweetId);
    if (created) {
      events.publish('tweet.liked', {
        tweet_id: tweetId,
        tweet_author_id: tweet.user_id,
        liked_by_id: req.user.id,
        liked_by_username: req.user.username,
      }, req.id);
    }
    return res.status(created ? 201 : 200).json({ tweet_id: tweetId, liked: true, count });
  }));

  app.delete('/api/likes/:tweetId', requireAuth, wrap(async (req, res) => {
    if (!/^\d+$/.test(req.params.tweetId)) return res.status(404).json({ detail: 'not found' });
    const tweetId = Number(req.params.tweetId);
    await db.removeLike(tweetId, req.user.id);
    const count = await db.countLikes(tweetId);
    return res.json({ tweet_id: tweetId, liked: false, count });
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

FILES["services/like-service/src/index.js"] = r'''const { createApp } = require('./app');
const { startConsumer } = require('./consumer');
const { createDb } = require('./db');
const { createEvents } = require('./events');
const { createEventHandler } = require('./handlers');
const { createLogger } = require('./logger');
const { createTweetClient } = require('./tweetClient');

function required(name) {
  if (!process.env[name]) throw new Error(`missing environment variable ${name}`);
  return process.env[name];
}

const config = {
  serviceName: process.env.SERVICE_NAME || 'like-service',
  port: Number(process.env.PORT || 8000),
  databaseUrl: required('DATABASE_URL'),
  rabbitmqUrl: process.env.RABBITMQ_URL || '',
  jwtSecret: required('JWT_SECRET'),
  tweetServiceUrl: process.env.TWEET_SERVICE_URL || 'http://tweet-service:8000',
};

async function main() {
  const logger = createLogger(config.serviceName);
  const db = createDb(config.databaseUrl, logger);
  await db.init();

  const events = createEvents({ url: config.rabbitmqUrl, serviceName: config.serviceName });
  const getTweet = createTweetClient({ baseUrl: config.tweetServiceUrl, serviceName: config.serviceName });
  const app = createApp({ config, db, events, getTweet });

  // Listen for "tweet.deleted" so the likes of a deleted tweet are removed.
  const consumer = startConsumer({
    url: config.rabbitmqUrl,
    serviceName: config.serviceName,
    queue: 'like-service.events',
    bindings: ['tweet.deleted'],
    onEvent: createEventHandler({ db, logger }),
  });

  const server = app.listen(config.port, () => logger.info(`listening on port ${config.port}`));

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

FILES["services/like-service/test/app.test.js"] = r'''process.env.LOG_SILENT = '1';

const test = require('node:test');
const assert = require('node:assert/strict');
const jwt = require('jsonwebtoken');
const { createApp } = require('../src/app');
const { createEventHandler } = require('../src/handlers');
const { createLogger } = require('../src/logger');

const SECRET = 'test-secret';
const adel = { id: 1, username: 'adel' };
const sara = { id: 2, username: 'sara' };

// Tweet 5 exists and was written by sara (user 2). Every other tweet id does not exist.
const TWEET = { id: 5, user_id: 2, username: 'sara', content: 'hello' };

function token(user, secret = SECRET) {
  return jwt.sign({ sub: String(user.id), username: user.username }, secret, {
    algorithm: 'HS256',
    expiresIn: '1h',
  });
}

function fakeDb() {
  const likes = new Map(); // "tweetId:userId" -> { tweetId, userId }
  return {
    likes,
    async addLike({ tweetId, userId }) {
      const key = `${tweetId}:${userId}`;
      if (likes.has(key)) return false;
      likes.set(key, { tweetId, userId });
      return true;
    },
    async removeLike(tweetId, userId) {
      likes.delete(`${tweetId}:${userId}`);
    },
    async countLikes(tweetId) {
      return [...likes.values()].filter((l) => l.tweetId === tweetId).length;
    },
    async likeSummary(ids, userId) {
      const summary = {};
      for (const id of ids) {
        const mine = [...likes.values()].filter((l) => l.tweetId === id);
        summary[id] = { count: mine.length, liked_by_me: mine.some((l) => l.userId === userId) };
      }
      return summary;
    },
    async deleteLikesForTweet(tweetId) {
      let removed = 0;
      for (const [key, like] of likes) {
        if (like.tweetId === tweetId) {
          likes.delete(key);
          removed++;
        }
      }
      return removed;
    },
    async ping() {},
  };
}

// Starts the app on a random port with a fake in-memory database and a fake event publisher.
async function start(overrides = {}) {
  const published = [];
  const db = fakeDb();
  const deps = {
    config: { serviceName: 'like-service', jwtSecret: SECRET },
    db,
    events: {
      publish(type, data) {
        published.push({ type, data });
      },
      async check() {
        return 'ok';
      },
    },
    getTweet: async (id) => (id === TWEET.id ? TWEET : null),
    ...overrides,
  };
  const server = await new Promise((resolve) => {
    const s = createApp(deps).listen(0, () => resolve(s));
  });
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    published,
    db,
    close: () =>
      new Promise((resolve) => {
        server.close(resolve);
        server.closeAllConnections();
      }),
  };
}

async function withApp(fn, overrides) {
  const app = await start(overrides);
  try {
    await fn(app);
  } finally {
    await app.close();
  }
}

function call(app, method, path, { body, as } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (as) headers.Authorization = `Bearer ${token(as)}`;
  return fetch(`${app.url}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
}

test('liking needs a token', () =>
  withApp(async (app) => {
    assert.equal((await call(app, 'POST', '/api/likes', { body: { tweet_id: 5 } })).status, 401);
  }));

test('a token signed with the wrong secret is rejected', () =>
  withApp(async (app) => {
    const res = await fetch(`${app.url}/api/likes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token(adel, 'other-secret')}` },
      body: JSON.stringify({ tweet_id: 5 }),
    });
    assert.equal(res.status, 401);
  }));

test('liking a tweet saves the like and publishes tweet.liked with the author', () =>
  withApp(async (app) => {
    const res = await call(app, 'POST', '/api/likes', { body: { tweet_id: 5 }, as: adel });
    assert.equal(res.status, 201);
    assert.deepEqual(await res.json(), { tweet_id: 5, liked: true, count: 1 });
    assert.equal(app.published.length, 1);
    assert.equal(app.published[0].type, 'tweet.liked');
    assert.deepEqual(app.published[0].data, {
      tweet_id: 5,
      tweet_author_id: 2,
      liked_by_id: 1,
      liked_by_username: 'adel',
    });
  }));

test('liking twice keeps one like and publishes only one event', () =>
  withApp(async (app) => {
    await call(app, 'POST', '/api/likes', { body: { tweet_id: 5 }, as: adel });
    const second = await call(app, 'POST', '/api/likes', { body: { tweet_id: 5 }, as: adel });
    assert.equal(second.status, 200);
    assert.equal((await second.json()).count, 1);
    assert.equal(app.published.length, 1);
  }));

test('two different users make the count 2', () =>
  withApp(async (app) => {
    await call(app, 'POST', '/api/likes', { body: { tweet_id: 5 }, as: adel });
    const res = await call(app, 'POST', '/api/likes', { body: { tweet_id: 5 }, as: sara });
    assert.equal((await res.json()).count, 2);
  }));

test('liking a tweet that does not exist is 404 and nothing is saved', () =>
  withApp(async (app) => {
    const res = await call(app, 'POST', '/api/likes', { body: { tweet_id: 99 }, as: adel });
    assert.equal(res.status, 404);
    assert.equal(app.db.likes.size, 0);
    assert.equal(app.published.length, 0);
  }));

test('when tweet-service is down nothing is saved and the answer is 503', () =>
  withApp(
    async (app) => {
      const res = await call(app, 'POST', '/api/likes', { body: { tweet_id: 5 }, as: adel });
      assert.equal(res.status, 503);
      assert.equal(app.db.likes.size, 0);
    },
    { getTweet: async () => { throw new Error('connection refused'); } }
  ));

test('a bad tweet_id is rejected', () =>
  withApp(async (app) => {
    assert.equal((await call(app, 'POST', '/api/likes', { body: { tweet_id: 'five' }, as: adel })).status, 422);
    assert.equal((await call(app, 'POST', '/api/likes', { body: {}, as: adel })).status, 422);
    assert.equal((await call(app, 'POST', '/api/likes', { body: { tweet_id: 0 }, as: adel })).status, 422);
  }));

test('unliking removes the like', () =>
  withApp(async (app) => {
    await call(app, 'POST', '/api/likes', { body: { tweet_id: 5 }, as: adel });
    const res = await call(app, 'DELETE', '/api/likes/5', { as: adel });
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { tweet_id: 5, liked: false, count: 0 });
  }));

test('unliking a tweet you never liked is harmless', () =>
  withApp(async (app) => {
    const res = await call(app, 'DELETE', '/api/likes/5', { as: adel });
    assert.equal(res.status, 200);
    assert.equal((await res.json()).count, 0);
  }));

test('the summary gives counts and liked_by_me for several tweets', () =>
  withApp(async (app) => {
    await call(app, 'POST', '/api/likes', { body: { tweet_id: 5 }, as: adel });
    await call(app, 'POST', '/api/likes', { body: { tweet_id: 5 }, as: sara });
    const asAdel = await (await call(app, 'GET', '/api/likes?tweet_ids=5,6', { as: adel })).json();
    assert.deepEqual(asAdel, { 5: { count: 2, liked_by_me: true }, 6: { count: 0, liked_by_me: false } });
    const asOther = await (await call(app, 'GET', '/api/likes?tweet_ids=5', { as: { id: 3, username: 'omar' } })).json();
    assert.deepEqual(asOther, { 5: { count: 2, liked_by_me: false } });
  }));

test('the summary needs a token and valid ids', () =>
  withApp(async (app) => {
    assert.equal((await call(app, 'GET', '/api/likes?tweet_ids=5')).status, 401);
    assert.equal((await call(app, 'GET', '/api/likes?tweet_ids=abc', { as: adel })).status, 422);
    assert.deepEqual(await (await call(app, 'GET', '/api/likes', { as: adel })).json(), {});
  }));

test('health and ready answer', () =>
  withApp(async (app) => {
    assert.equal((await (await call(app, 'GET', '/health')).json()).status, 'ok');
    const ready = await call(app, 'GET', '/ready');
    assert.equal(ready.status, 200);
    assert.equal((await ready.json()).checks.database, 'ok');
  }));

// ---- what happens when an event arrives ----
test('tweet.deleted removes all the likes of that tweet', async () => {
  const db = fakeDb();
  await db.addLike({ tweetId: 5, userId: 1 });
  await db.addLike({ tweetId: 5, userId: 2 });
  await db.addLike({ tweetId: 6, userId: 1 });
  const handle = createEventHandler({ db, logger: createLogger('like-service') });

  await handle({ id: 'e1', type: 'tweet.deleted', data: { tweet_id: 5, user_id: 2 } });

  assert.equal(await db.countLikes(5), 0);
  assert.equal(await db.countLikes(6), 1);
});

test('events that are not for like-service are ignored', async () => {
  const db = fakeDb();
  await db.addLike({ tweetId: 5, userId: 1 });
  const handle = createEventHandler({ db, logger: createLogger('like-service') });

  await handle({ id: 'e2', type: 'user.registered', data: { user_id: 9 } });

  assert.equal(await db.countLikes(5), 1);
});

test('tweet.deleted without a tweet id is an error', async () => {
  const handle = createEventHandler({ db: fakeDb(), logger: createLogger('like-service') });
  await assert.rejects(() => handle({ id: 'e3', type: 'tweet.deleted', data: {} }));
});
'''

# ---------------------------------------------------------------------------
# frontend changes
# ---------------------------------------------------------------------------
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

FILES["frontend/src/components/Feed.tsx"] = r'''import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { createTweet, deleteTweet, getLikes, likeTweet, listTweets, unlikeTweet } from "../api";
import type { LikeInfo, Tweet, User } from "../api";

function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong";
}

export default function Feed({ user }: { user: User }) {
  const [tweets, setTweets] = useState<Tweet[] | null>(null);
  const [likes, setLikes] = useState<Record<string, LikeInfo>>({});
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await listTweets();
      setTweets(list);
      setLoadError("");
      if (list.length > 0) {
        try {
          setLikes(await getLikes(list.map((t) => t.id)));
        } catch {
          // Likes are optional: if like-service is down the tweets still show.
        }
      }
    } catch (err) {
      setLoadError(messageOf(err));
    }
  }, []);

  // Load now, then refresh every 5 seconds so tweets and likes from other accounts show up.
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load]);

  async function post(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    setError("");
    setBusy(true);
    try {
      await createTweet(text.trim());
      setText("");
      await load();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    setError("");
    try {
      await deleteTweet(id);
      await load();
    } catch (err) {
      setError(messageOf(err));
    }
  }

  async function toggleLike(tweet: Tweet) {
    setError("");
    const liked = likes[String(tweet.id)]?.liked_by_me === true;
    try {
      const result = liked ? await unlikeTweet(tweet.id) : await likeTweet(tweet.id);
      setLikes((old) => ({
        ...old,
        [String(tweet.id)]: { count: result.count, liked_by_me: result.liked },
      }));
    } catch (err) {
      setError(messageOf(err));
    }
  }

  const left = 280 - text.length;

  return (
    <div className="space-y-4">
      <form
        onSubmit={post}
        className="rounded-2xl border border-black/5 bg-card p-5 shadow-sm dark:border-white/10 dark:bg-card-dark"
      >
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={280}
          rows={3}
          placeholder="What's happening?"
          className="w-full resize-none rounded-xl border border-black/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/30 dark:border-white/10 dark:bg-surface-dark"
        />
        <div className="mt-3 flex items-center justify-between">
          <span className={`text-xs ${left < 20 ? "text-accent" : "opacity-60"}`}>{left} left</span>
          <button
            type="submit"
            disabled={busy || !text.trim()}
            className="rounded-full bg-brand px-5 py-2 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {busy ? "Posting..." : "Post"}
          </button>
        </div>
      </form>

      {error && (
        <div className="rounded-xl bg-red-100 px-4 py-2 text-sm text-red-700 dark:bg-red-900/40 dark:text-red-300">
          {error}
        </div>
      )}

      {loadError && (
        <div className="rounded-xl bg-amber-100 px-4 py-2 text-sm text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
          Could not load tweets: {loadError}
        </div>
      )}

      {tweets === null && !loadError && (
        <div className="space-y-3">
          <div className="h-24 animate-pulse rounded-2xl bg-black/5 dark:bg-white/10" />
          <div className="h-24 animate-pulse rounded-2xl bg-black/5 dark:bg-white/10" />
        </div>
      )}

      {tweets !== null && tweets.length === 0 && (
        <div className="rounded-2xl border border-dashed border-black/10 p-8 text-center text-sm opacity-70 dark:border-white/20">
          No tweets yet. Be the first to post.
        </div>
      )}

      {tweets?.map((tweet) => {
        const info = likes[String(tweet.id)];
        const liked = info?.liked_by_me === true;
        return (
          <article
            key={tweet.id}
            className="rounded-2xl border border-black/5 bg-card p-5 shadow-sm dark:border-white/10 dark:bg-card-dark"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand to-accent font-bold uppercase text-white">
                {tweet.username.charAt(0)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm">
                    <span className="font-bold">@{tweet.username}</span>
                    <span className="ml-2 opacity-60">{timeAgo(tweet.created_at)}</span>
                  </p>
                  {tweet.user_id === user.id && (
                    <button
                      onClick={() => void remove(tweet.id)}
                      className="rounded-full px-3 py-1 text-xs font-semibold text-red-500 transition hover:bg-red-500/10"
                    >
                      Delete
                    </button>
                  )}
                </div>
                <p className="mt-1 whitespace-pre-wrap break-words text-sm">{tweet.content}</p>
                <button
                  onClick={() => void toggleLike(tweet)}
                  aria-label={liked ? "Unlike this tweet" : "Like this tweet"}
                  className={`mt-3 flex items-center gap-1.5 rounded-full px-3 py-1 text-sm transition hover:bg-accent/10 ${
                    liked ? "font-semibold text-accent" : "opacity-70"
                  }`}
                >
                  <span>{liked ? "♥" : "♡"}</span>
                  <span>{info?.count ?? 0}</span>
                </button>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
'''

FILES["frontend/src/components/SystemPanel.tsx"] = r'''const SERVICES = [
  { name: "user-service", tech: "Python", state: "built" },
  { name: "tweet-service", tech: "Node.js", state: "built" },
  { name: "like-service", tech: "Node.js", state: "built" },
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
    parser = argparse.ArgumentParser(description="MiniTweet v2 - step 3 setup")
    parser.add_argument("--force", action="store_true", help="also overwrite files you edited (.bak saved)")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list files left alone")
    args = parser.parse_args()

    root = Path.cwd()
    if not (root / "services" / "tweet-service" / "src" / "app.js").exists() or not (root / "docker-compose.yml").exists():
        print("Step 2 is not in this folder. Run this script inside the folder where step 2 works.")
        return 1

    counts = {"created": 0, "updated": 0, "kept": 0}
    print(f"MiniTweet step 3 in: {root}" + ("  [dry run]" if args.dry_run else ""))

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
