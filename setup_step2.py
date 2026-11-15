#!/usr/bin/env python3
"""
MiniTweet v2 - Step 2: tweet-service (Node.js) + feed screen.

Run it in the same folder where step 1 already works:

    python setup_step2.py              # add everything for step 2
    python setup_step2.py --dry-run    # show what would happen, change nothing
    python setup_step2.py -v           # also list files that were left alone
    python setup_step2.py --force      # also overwrite files you edited (a .bak copy is saved)

Safe to run again. Shared files that step 2 changes (docker-compose.yml, nginx.conf,
App.tsx, api.ts, Profile.tsx, SystemPanel.tsx) are replaced and the old copy is
saved next to them as <name>.bak. Files you edited that step 2 does not own are
left alone.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Files from step 1 that step 2 replaces (a .bak copy is saved first).
MANAGED = {
    "docker-compose.yml",
    "frontend/nginx.conf",
    "frontend/src/App.tsx",
    "frontend/src/api.ts",
    "frontend/src/components/Profile.tsx",
    "frontend/src/components/SystemPanel.tsx",
}

FILES: dict[str, str] = {}

# ---------------------------------------------------------------------------
# docker-compose (step 1 services + tweet-db + tweet-service)
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

  # ---------- frontend ----------
  frontend:
    build: ./frontend
    restart: unless-stopped
    ports:
      - "8080:80"
    depends_on:
      - user-service
      - tweet-service

volumes:
  user_db_data:
  tweet_db_data:
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

    location / {
        try_files $uri /index.html;
    }
}
'''

# ---------------------------------------------------------------------------
# tweet-service (Node.js / Express)
# ---------------------------------------------------------------------------
FILES["services/tweet-service/package.json"] = r'''{
  "name": "tweet-service",
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

FILES["services/tweet-service/Dockerfile"] = r'''FROM node:20-alpine
ENV NODE_ENV=production
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY src ./src

USER node
EXPOSE 8000
CMD ["node", "src/index.js"]
'''

FILES["services/tweet-service/.dockerignore"] = r'''node_modules
test
npm-debug.log
'''

FILES["services/tweet-service/src/logger.js"] = r'''// One JSON object per line, same field names in every service (see docs/contracts.md).
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

FILES["services/tweet-service/src/db.js"] = r'''const { Pool } = require('pg');

function createDb(connectionString, logger) {
  const pool = new Pool({ connectionString, max: 5 });
  pool.on('error', (err) => logger.warn(`database connection error: ${err.message}`));
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const columns = 'id, user_id, username, content, created_at';

  return {
    // Create the table. Retries because the database may still be starting.
    async init() {
      for (let attempt = 1; attempt <= 30; attempt++) {
        try {
          await pool.query(`
            CREATE TABLE IF NOT EXISTS tweets (
              id SERIAL PRIMARY KEY,
              user_id INTEGER NOT NULL,
              username VARCHAR(20) NOT NULL,
              content VARCHAR(280) NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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

    async insertTweet({ userId, username, content }) {
      const { rows } = await pool.query(
        `INSERT INTO tweets (user_id, username, content) VALUES ($1, $2, $3) RETURNING ${columns}`,
        [userId, username, content]
      );
      return rows[0];
    },

    async listTweets(limit) {
      const { rows } = await pool.query(`SELECT ${columns} FROM tweets ORDER BY id DESC LIMIT $1`, [limit]);
      return rows;
    },

    async getTweet(id) {
      const { rows } = await pool.query(`SELECT ${columns} FROM tweets WHERE id = $1`, [id]);
      return rows[0] || null;
    },

    async deleteTweet(id) {
      await pool.query('DELETE FROM tweets WHERE id = $1', [id]);
    },

    async close() {
      await pool.end();
    },
  };
}

module.exports = { createDb };
'''

FILES["services/tweet-service/src/events.js"] = r'''const crypto = require('crypto');
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

FILES["services/tweet-service/src/userClient.js"] = r'''// Asks user-service "who is user N?" over REST.
// Returns the user, or null if the user does not exist. Throws if user-service cannot be reached.
function createUserClient({ baseUrl, serviceName }) {
  return async function getUser(id, requestId) {
    let lastError;
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const response = await fetch(`${baseUrl}/api/users/${id}`, {
          headers: { 'X-Caller': serviceName, 'X-Request-ID': requestId },
          signal: AbortSignal.timeout(3000),
        });
        if (response.status === 404) return null;
        if (!response.ok) throw new Error(`user-service answered ${response.status}`);
        return await response.json();
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError;
  };
}

module.exports = { createUserClient };
'''

FILES["services/tweet-service/src/app.js"] = r'''const crypto = require('crypto');
const express = require('express');
const jwt = require('jsonwebtoken');
const { createLogger } = require('./logger');

// The app is built from its dependencies so the tests can plug in fakes.
function createApp({ config, db, events, getUser }) {
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
  const parseId = (text) => (/^\d+$/.test(text) ? Number(text) : null);

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

  app.get(['/health', '/api/tweets/health'], (req, res) => {
    res.json({ status: 'ok', service: config.serviceName });
  });

  // Ready means "I can do my job". RabbitMQ is reported but optional,
  // because publishing events is best effort.
  app.get(['/ready', '/api/tweets/ready'], wrap(async (req, res) => {
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

  // Latest tweets, newest first. Public.
  app.get('/api/tweets', wrap(async (req, res) => {
    const limit = Math.min(Math.max(parseInt(req.query.limit, 10) || 20, 1), 50);
    res.json(await db.listTweets(limit));
  }));

  // One tweet. Other services (like-service) use this.
  app.get('/api/tweets/:id', wrap(async (req, res) => {
    const id = parseId(req.params.id);
    const tweet = id === null ? null : await db.getTweet(id);
    if (!tweet) return res.status(404).json({ detail: 'tweet not found' });
    return res.json(tweet);
  }));

  app.post('/api/tweets', requireAuth, wrap(async (req, res) => {
    const content = typeof req.body?.content === 'string' ? req.body.content.trim() : '';
    if (content.length < 1 || content.length > 280) {
      return res.status(422).json({ detail: 'content must be 1 to 280 characters' });
    }

    // REST call to user-service: does this account still exist, and what is its name?
    let author;
    try {
      author = await getUser(req.user.id, req.id);
    } catch (err) {
      req.log.error('user-service call failed', { error: err.message });
      return res.status(503).json({ detail: 'user-service is unavailable, try again' });
    }
    if (!author) return res.status(401).json({ detail: 'user no longer exists' });

    const tweet = await db.insertTweet({ userId: author.id, username: author.username, content });
    events.publish('tweet.created', {
      tweet_id: tweet.id,
      user_id: tweet.user_id,
      username: tweet.username,
    }, req.id);
    return res.status(201).json(tweet);
  }));

  app.delete('/api/tweets/:id', requireAuth, wrap(async (req, res) => {
    const id = parseId(req.params.id);
    const tweet = id === null ? null : await db.getTweet(id);
    if (!tweet) return res.status(404).json({ detail: 'tweet not found' });
    if (tweet.user_id !== req.user.id) {
      return res.status(403).json({ detail: 'you can only delete your own tweets' });
    }
    await db.deleteTweet(id);
    events.publish('tweet.deleted', { tweet_id: id, user_id: tweet.user_id }, req.id);
    return res.status(204).end();
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

FILES["services/tweet-service/src/index.js"] = r'''const { createApp } = require('./app');
const { createDb } = require('./db');
const { createEvents } = require('./events');
const { createLogger } = require('./logger');
const { createUserClient } = require('./userClient');

function required(name) {
  if (!process.env[name]) throw new Error(`missing environment variable ${name}`);
  return process.env[name];
}

const config = {
  serviceName: process.env.SERVICE_NAME || 'tweet-service',
  port: Number(process.env.PORT || 8000),
  databaseUrl: required('DATABASE_URL'),
  rabbitmqUrl: process.env.RABBITMQ_URL || '',
  jwtSecret: required('JWT_SECRET'),
  userServiceUrl: process.env.USER_SERVICE_URL || 'http://user-service:8000',
};

async function main() {
  const logger = createLogger(config.serviceName);
  const db = createDb(config.databaseUrl, logger);
  await db.init();

  const events = createEvents({ url: config.rabbitmqUrl, serviceName: config.serviceName });
  const getUser = createUserClient({ baseUrl: config.userServiceUrl, serviceName: config.serviceName });
  const app = createApp({ config, db, events, getUser });

  const server = app.listen(config.port, () => logger.info(`listening on port ${config.port}`));

  // Stop cleanly when Docker or Kubernetes asks us to.
  const shutdown = () => {
    logger.info('shutting down');
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

FILES["services/tweet-service/test/app.test.js"] = r'''process.env.LOG_SILENT = '1';

const test = require('node:test');
const assert = require('node:assert/strict');
const jwt = require('jsonwebtoken');
const { createApp } = require('../src/app');

const SECRET = 'test-secret';
const adel = { id: 1, username: 'adel' };
const sara = { id: 2, username: 'sara' };

function token(user, secret = SECRET) {
  return jwt.sign({ sub: String(user.id), username: user.username }, secret, {
    algorithm: 'HS256',
    expiresIn: '1h',
  });
}

// Starts the app on a random port with a fake in-memory database and a fake event publisher.
async function start(overrides = {}) {
  const tweets = [];
  const published = [];
  let nextId = 1;
  const deps = {
    config: { serviceName: 'tweet-service', jwtSecret: SECRET },
    db: {
      async insertTweet({ userId, username, content }) {
        const tweet = { id: nextId++, user_id: userId, username, content, created_at: new Date().toISOString() };
        tweets.push(tweet);
        return tweet;
      },
      async listTweets(limit) {
        return [...tweets].reverse().slice(0, limit);
      },
      async getTweet(id) {
        return tweets.find((t) => t.id === id) || null;
      },
      async deleteTweet(id) {
        const index = tweets.findIndex((t) => t.id === id);
        if (index >= 0) tweets.splice(index, 1);
      },
      async ping() {},
    },
    events: {
      publish(type, data) {
        published.push({ type, data });
      },
      async check() {
        return 'ok';
      },
    },
    getUser: async (id) => ({ id, username: id === 1 ? 'adel' : 'sara' }),
    ...overrides,
  };
  const server = await new Promise((resolve) => {
    const s = createApp(deps).listen(0, () => resolve(s));
  });
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    published,
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

test('posting a tweet needs a token', () =>
  withApp(async (app) => {
    const res = await call(app, 'POST', '/api/tweets', { body: { content: 'hi' } });
    assert.equal(res.status, 401);
  }));

test('a token signed with the wrong secret is rejected', () =>
  withApp(async (app) => {
    const res = await fetch(`${app.url}/api/tweets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token(adel, 'other-secret')}` },
      body: JSON.stringify({ content: 'hi' }),
    });
    assert.equal(res.status, 401);
  }));

test('posting saves the tweet with the username from user-service and publishes tweet.created', () =>
  withApp(async (app) => {
    const res = await call(app, 'POST', '/api/tweets', { body: { content: '  my first tweet  ' }, as: adel });
    assert.equal(res.status, 201);
    const tweet = await res.json();
    assert.equal(tweet.content, 'my first tweet');
    assert.equal(tweet.username, 'adel');
    assert.equal(app.published.length, 1);
    assert.equal(app.published[0].type, 'tweet.created');
    assert.equal(app.published[0].data.tweet_id, tweet.id);
  }));

test('empty and too long tweets are rejected', () =>
  withApp(async (app) => {
    assert.equal((await call(app, 'POST', '/api/tweets', { body: { content: '   ' }, as: adel })).status, 422);
    assert.equal((await call(app, 'POST', '/api/tweets', { body: { content: 'x'.repeat(281) }, as: adel })).status, 422);
    assert.equal(app.published.length, 0);
  }));

test('when user-service is down the tweet is not saved and the answer is 503', () =>
  withApp(
    async (app) => {
      const res = await call(app, 'POST', '/api/tweets', { body: { content: 'hello' }, as: adel });
      assert.equal(res.status, 503);
      const list = await (await call(app, 'GET', '/api/tweets')).json();
      assert.equal(list.length, 0);
    },
    { getUser: async () => { throw new Error('connection refused'); } }
  ));

test('a token for a user that no longer exists is rejected', () =>
  withApp(
    async (app) => {
      const res = await call(app, 'POST', '/api/tweets', { body: { content: 'hello' }, as: adel });
      assert.equal(res.status, 401);
    },
    { getUser: async () => null }
  ));

test('the list shows the newest tweet first', () =>
  withApp(async (app) => {
    await call(app, 'POST', '/api/tweets', { body: { content: 'first' }, as: adel });
    await call(app, 'POST', '/api/tweets', { body: { content: 'second' }, as: sara });
    const list = await (await call(app, 'GET', '/api/tweets')).json();
    assert.deepEqual(list.map((t) => t.content), ['second', 'first']);
  }));

test('a single tweet can be read by id, and an unknown id is 404', () =>
  withApp(async (app) => {
    const created = await (await call(app, 'POST', '/api/tweets', { body: { content: 'hello' }, as: adel })).json();
    const found = await call(app, 'GET', `/api/tweets/${created.id}`);
    assert.equal(found.status, 200);
    assert.equal((await found.json()).user_id, 1);
    assert.equal((await call(app, 'GET', '/api/tweets/999')).status, 404);
    assert.equal((await call(app, 'GET', '/api/tweets/abc')).status, 404);
  }));

test('you can delete your own tweet, and tweet.deleted is published', () =>
  withApp(async (app) => {
    const created = await (await call(app, 'POST', '/api/tweets', { body: { content: 'bye' }, as: adel })).json();
    const res = await call(app, 'DELETE', `/api/tweets/${created.id}`, { as: adel });
    assert.equal(res.status, 204);
    assert.equal((await call(app, 'GET', `/api/tweets/${created.id}`)).status, 404);
    assert.equal(app.published[app.published.length - 1].type, 'tweet.deleted');
  }));

test('you cannot delete someone else\'s tweet', () =>
  withApp(async (app) => {
    const created = await (await call(app, 'POST', '/api/tweets', { body: { content: 'mine' }, as: adel })).json();
    const res = await call(app, 'DELETE', `/api/tweets/${created.id}`, { as: sara });
    assert.equal(res.status, 403);
    assert.equal((await call(app, 'GET', `/api/tweets/${created.id}`)).status, 200);
  }));

test('deleting needs a token and a real tweet', () =>
  withApp(async (app) => {
    assert.equal((await call(app, 'DELETE', '/api/tweets/1')).status, 401);
    assert.equal((await call(app, 'DELETE', '/api/tweets/999', { as: adel })).status, 404);
  }));

test('health and ready answer', () =>
  withApp(async (app) => {
    const health = await call(app, 'GET', '/health');
    assert.equal((await health.json()).status, 'ok');
    const ready = await call(app, 'GET', '/ready');
    assert.equal(ready.status, 200);
    assert.equal((await ready.json()).checks.database, 'ok');
  }));
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

import { createTweet, deleteTweet, listTweets } from "../api";
import type { Tweet, User } from "../api";

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
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setTweets(await listTweets());
      setLoadError("");
    } catch (err) {
      setLoadError(messageOf(err));
    }
  }, []);

  // Load now, then refresh every 5 seconds so tweets from other accounts show up.
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
        {error && (
          <div className="mt-3 rounded-xl bg-red-100 px-4 py-2 text-sm text-red-700 dark:bg-red-900/40 dark:text-red-300">
            {error}
          </div>
        )}
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

      {tweets?.map((tweet) => (
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
            </div>
          </div>
        </article>
      ))}
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
    <div className="rounded-2xl border border-black/5 bg-card p-5 shadow-sm dark:border-white/10 dark:bg-card-dark">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-brand to-accent text-xl font-bold uppercase text-white">
            {user.username.charAt(0)}
          </div>
          <div>
            <h2 className="text-lg font-extrabold tracking-tight">@{user.username}</h2>
            <p className="text-xs opacity-70">User #{user.id}</p>
          </div>
        </div>
        <button
          onClick={onLogout}
          className="rounded-full border border-black/10 px-4 py-2 text-sm font-semibold transition hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
        >
          Log out
        </button>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-xs font-semibold opacity-70">Show my login token</summary>
        <p className="mt-2 text-xs opacity-70">
          This is what user-service gave you. Every other service checks it the same way.
          {exp !== null && ` Expires at ${new Date(exp * 1000).toLocaleTimeString()}.`}
        </p>
        <pre className="mt-2 overflow-x-auto rounded-xl bg-black/5 p-3 text-xs dark:bg-white/10">
          {JSON.stringify(claims, null, 2)}
        </pre>
      </details>
    </div>
  );
}
'''

FILES["frontend/src/components/SystemPanel.tsx"] = r'''const SERVICES = [
  { name: "user-service", tech: "Python", state: "built" },
  { name: "tweet-service", tech: "Node.js", state: "built" },
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
import Feed from "./components/Feed";
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
            <div className="space-y-4">
              <Profile user={user} onLogout={logout} />
              <Feed user={user} />
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
    parser = argparse.ArgumentParser(description="MiniTweet v2 - step 2 setup")
    parser.add_argument("--force", action="store_true", help="also overwrite files you edited (.bak saved)")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list files left alone")
    args = parser.parse_args()

    root = Path.cwd()
    if not (root / "services" / "user-service" / "app.py").exists() or not (root / "docker-compose.yml").exists():
        print("Step 1 is not in this folder. Run this script inside the folder where step 1 works.")
        return 1

    counts = {"created": 0, "updated": 0, "kept": 0}
    print(f"MiniTweet step 2 in: {root}" + ("  [dry run]" if args.dry_run else ""))

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
