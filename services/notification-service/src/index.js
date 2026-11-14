const express = require('express');

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
