const { Pool } = require('pg');

function createDb(connectionString, logger) {
  const pool = new Pool({ connectionString, max: 5 });
  pool.on('error', (err) => logger.warn(`database connection error: ${err.message}`));
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  return {
    // Create the table. Retries because the database may still be starting.
    async init() {
      for (let attempt = 1; attempt <= 30; attempt++) {
        try {
          await pool.query(`
            CREATE TABLE IF NOT EXISTS notifications (
              id SERIAL PRIMARY KEY,
              user_id INTEGER NOT NULL,
              type VARCHAR(30) NOT NULL,
              message VARCHAR(200) NOT NULL,
              tweet_id INTEGER,
              event_id VARCHAR(64) NOT NULL UNIQUE,
              is_read BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )`);
          await pool.query('CREATE INDEX IF NOT EXISTS notifications_user_idx ON notifications (user_id, id DESC)');
          logger.info('database ready');
          return;
        } catch (err) {
          logger.warn(`database not ready (${err.message}), retry ${attempt}/30`);
          await sleep(2000);
        }
      }
      throw new Error('database never became ready');
    },

    async ping() {
      await pool.query('SELECT 1');
    },

    // Returns true if saved, false if this event had already been handled (same event id).
    async addNotification({ userId, type, message, tweetId, eventId }) {
      const { rows } = await pool.query(
        `INSERT INTO notifications (user_id, type, message, tweet_id, event_id)
         VALUES ($1, $2, $3, $4, $5) ON CONFLICT (event_id) DO NOTHING RETURNING id`,
        [userId, type, message, tweetId, eventId]
      );
      return rows.length > 0;
    },

    async listForUser(userId, limit) {
      const { rows } = await pool.query(
        `SELECT id, type, message, tweet_id, is_read, created_at
         FROM notifications WHERE user_id = $1 ORDER BY id DESC LIMIT $2`,
        [userId, limit]
      );
      return rows;
    },

    async countUnread(userId) {
      const { rows } = await pool.query(
        'SELECT COUNT(*)::int AS count FROM notifications WHERE user_id = $1 AND NOT is_read',
        [userId]
      );
      return rows[0].count;
    },

    async markAllRead(userId) {
      await pool.query('UPDATE notifications SET is_read = TRUE WHERE user_id = $1 AND NOT is_read', [userId]);
    },

    async close() {
      await pool.end();
    },
  };
}

module.exports = { createDb };
