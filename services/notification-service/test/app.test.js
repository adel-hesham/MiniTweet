process.env.LOG_SILENT = '1';

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
