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

test('tokens with a missing or non-numeric subject are rejected', () =>
  withApp(async (app) => {
    const noSub = jwt.sign({ username: 'adel' }, SECRET, { algorithm: 'HS256', expiresIn: '1h' });
    const badSub = jwt.sign({ sub: 'not-a-number', username: 'adel' }, SECRET, { algorithm: 'HS256', expiresIn: '1h' });

    const missing = await fetch(`${app.url}/api/likes?tweet_ids=5`, {
      headers: { Authorization: `Bearer ${noSub}` },
    });
    assert.equal(missing.status, 401);

    const invalid = await fetch(`${app.url}/api/likes?tweet_ids=5`, {
      headers: { Authorization: `Bearer ${badSub}` },
    });
    assert.equal(invalid.status, 401);
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
