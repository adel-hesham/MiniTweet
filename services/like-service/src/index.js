const { createApp } = require('./app');
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
