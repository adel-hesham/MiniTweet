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
            CREATE TABLE IF NOT EXISTS likes (
              id SERIAL PRIMARY KEY,
              tweet_id INTEGER NOT NULL,
              user_id INTEGER NOT NULL,
              username VARCHAR(20) NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              UNIQUE (tweet_id, user_id)
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

    // Returns true if the like is new, false if the user had already liked this tweet.
    async addLike({ tweetId, userId, username }) {
      const { rows } = await pool.query(
        `INSERT INTO likes (tweet_id, user_id, username) VALUES ($1, $2, $3)
         ON CONFLICT (tweet_id, user_id) DO NOTHING RETURNING id`,
        [tweetId, userId, username]
      );
      return rows.length > 0;
    },

    async removeLike(tweetId, userId) {
      await pool.query('DELETE FROM likes WHERE tweet_id = $1 AND user_id = $2', [tweetId, userId]);
    },

    async countLikes(tweetId) {
      const { rows } = await pool.query('SELECT COUNT(*)::int AS count FROM likes WHERE tweet_id = $1', [tweetId]);
      return rows[0].count;
    },

    // { "5": { count: 2, liked_by_me: true }, ... } with an entry for every id asked for.
    async likeSummary(tweetIds, userId) {
      const { rows } = await pool.query(
        `SELECT tweet_id, COUNT(*)::int AS count, BOOL_OR(user_id = $2) AS liked_by_me
         FROM likes WHERE tweet_id = ANY($1::int[]) GROUP BY tweet_id`,
        [tweetIds, userId]
      );
      const summary = {};
      for (const id of tweetIds) summary[id] = { count: 0, liked_by_me: false };
      for (const row of rows) summary[row.tweet_id] = { count: row.count, liked_by_me: row.liked_by_me };
      return summary;
    },

    async deleteLikesForTweet(tweetId) {
      const result = await pool.query('DELETE FROM likes WHERE tweet_id = $1', [tweetId]);
      return result.rowCount;
    },

    async close() {
      await pool.end();
    },
  };
}

module.exports = { createDb };
