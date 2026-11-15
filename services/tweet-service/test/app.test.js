process.env.LOG_SILENT = '1';

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

test('tokens with a missing or non-numeric subject are rejected', () =>
  withApp(async (app) => {
    const noSub = jwt.sign({ username: 'adel' }, SECRET, { algorithm: 'HS256', expiresIn: '1h' });
    const badSub = jwt.sign({ sub: '1e3', username: 'adel' }, SECRET, { algorithm: 'HS256', expiresIn: '1h' });

    const missing = await fetch(`${app.url}/api/tweets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${noSub}` },
      body: JSON.stringify({ content: 'hi' }),
    });
    assert.equal(missing.status, 401);

    const invalid = await fetch(`${app.url}/api/tweets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${badSub}` },
      body: JSON.stringify({ content: 'hi' }),
    });
    assert.equal(invalid.status, 401);
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
