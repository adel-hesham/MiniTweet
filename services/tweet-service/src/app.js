const crypto = require('crypto');
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
      const rawSub = claims.sub;
      if (typeof rawSub !== 'string' || !/^\d+$/.test(rawSub)) {
        return res.status(401).json({ detail: 'invalid or expired token' });
      }
      const userId = Number(rawSub);
      if (!Number.isSafeInteger(userId) || userId <= 0) {
        return res.status(401).json({ detail: 'invalid or expired token' });
      }
      req.user = { id: userId, username: claims.username };
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
