const amqp = require('amqplib');
const { createLogger } = require('./logger');

const EXCHANGE = 'minitweet';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Listens to events and hands each one to onEvent. Reconnects by itself if RabbitMQ goes away.
function startConsumer({ url, serviceName, queue, bindings, onEvent }) {
  const log = createLogger(serviceName);
  let stopped = false;
  let currentConnection = null;

  async function listen(connection) {
    const channel = await connection.createChannel();
    await channel.assertExchange(EXCHANGE, 'topic', { durable: true });
    await channel.assertQueue(queue, { durable: true });
    for (const key of bindings) await channel.bindQueue(queue, EXCHANGE, key);
    await channel.prefetch(10);
    await channel.consume(queue, async (msg) => {
      if (msg === null) return;

      let event;
      try {
        event = JSON.parse(msg.content.toString());
        if (!event || typeof event !== 'object') throw new Error('not an object');
      } catch {
        log.error('dropping a message that is not a valid event');
        channel.ack(msg);
        return;
      }

      try {
        await onEvent(event);
        channel.ack(msg);
      } catch (err) {
        // Try once more. After that give up on this message so it cannot block the queue.
        const retry = !msg.fields.redelivered;
        log.error(`failed to handle ${event.type}: ${err.message}`, { event_id: event.id, will_retry: retry });
        channel.nack(msg, false, retry);
      }
    });
    log.info(`listening for events on queue ${queue}`, { bindings: bindings.join(',') });
  }

  async function loop() {
    while (!stopped) {
      try {
        const connection = await amqp.connect(url);
        currentConnection = connection;
        await new Promise((resolve) => {
          connection.on('error', (err) => log.warn(`RabbitMQ error: ${err.message}`));
          connection.on('close', resolve);
          listen(connection).catch((err) => {
            log.error(`could not start listening: ${err.message}`);
            connection.close().catch(() => {});
          });
        });
        if (!stopped) log.warn('RabbitMQ connection lost, reconnecting in 5s');
      } catch (err) {
        log.warn(`cannot reach RabbitMQ (${err.message}), retrying in 5s`);
      }
      if (!stopped) await sleep(5000);
    }
  }

  if (url) loop();

  return {
    async stop() {
      stopped = true;
      if (currentConnection) await currentConnection.close().catch(() => {});
    },
  };
}

module.exports = { startConsumer };
