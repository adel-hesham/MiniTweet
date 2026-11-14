const crypto = require('crypto');
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
