const { createApp } = require('./app');
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
