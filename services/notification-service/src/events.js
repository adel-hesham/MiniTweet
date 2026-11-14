const crypto = require('crypto');
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
