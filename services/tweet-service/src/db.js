const { Pool } = require('pg');

function createDb(connectionString, logger) {
  const pool = new Pool({ connectionString, max: 5 });
  pool.on('error', (err) => logger.warn(`database connection error: ${err.message}`));
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const columns = 'id, user_id, username, content, created_at';

  return {
    // Create the table. Retries because the database may still be starting.
    async init() {
      for (let attempt = 1; attempt <= 30; attempt++) {
        try {
          await pool.query(`
            CREATE TABLE IF NOT EXISTS tweets (
              id SERIAL PRIMARY KEY,
              user_id INTEGER NOT NULL,
              username VARCHAR(20) NOT NULL,
              content VARCHAR(280) NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )`);
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

    async insertTweet({ userId, username, content }) {
      const { rows } = await pool.query(
        `INSERT INTO tweets (user_id, username, content) VALUES ($1, $2, $3) RETURNING ${columns}`,
        [userId, username, content]
      );
      return rows[0];
    },

    async listTweets(limit) {
      const { rows } = await pool.query(`SELECT ${columns} FROM tweets ORDER BY id DESC LIMIT $1`, [limit]);
      return rows;
    },

    async getTweet(id) {
      const { rows } = await pool.query(`SELECT ${columns} FROM tweets WHERE id = $1`, [id]);
      return rows[0] || null;
    },

    async deleteTweet(id) {
      await pool.query('DELETE FROM tweets WHERE id = $1', [id]);
    },

    async close() {
      await pool.end();
    },
  };
}

module.exports = { createDb };
