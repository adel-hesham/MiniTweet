// What like-service does when an event arrives.
function createEventHandler({ db, logger }) {
  return async function handle(event) {
    if (event.type === 'tweet.deleted') {
      const tweetId = event.data && event.data.tweet_id;
      if (!Number.isInteger(tweetId)) throw new Error('tweet.deleted without a tweet_id');
      const removed = await db.deleteLikesForTweet(tweetId);
      logger.info(`removed ${removed} like(s) of deleted tweet ${tweetId}`, { event_id: event.id });
    }
    // Any other event is not for us: ignore it.
  };
}

module.exports = { createEventHandler };
