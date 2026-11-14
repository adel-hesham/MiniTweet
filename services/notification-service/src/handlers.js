// What notification-service does when an event arrives.
// Each notification remembers the id of the event that made it, so if the same event is
// delivered twice the second one is ignored (no double notifications).
function createEventHandler({ db, logger }) {
  return async function handle(event) {
    const data = event.data || {};

    if (event.type === 'user.registered') {
      if (!Number.isInteger(data.user_id)) throw new Error('user.registered without a user_id');
      await db.addNotification({
        userId: data.user_id,
        type: 'welcome',
        message: `Welcome to MiniTweet, @${data.username}!`.slice(0, 200),
        tweetId: null,
        eventId: event.id,
      });
      logger.info(`welcome notification for user ${data.user_id}`, { event_id: event.id });
      return;
    }

    if (event.type === 'tweet.liked') {
      if (!Number.isInteger(data.tweet_author_id) || !Number.isInteger(data.liked_by_id)) {
        throw new Error('tweet.liked without tweet_author_id or liked_by_id');
      }
      // Nobody needs a notification about liking their own tweet.
      if (data.tweet_author_id === data.liked_by_id) return;
      await db.addNotification({
        userId: data.tweet_author_id,
        type: 'like',
        message: `@${data.liked_by_username} liked your tweet`.slice(0, 200),
        tweetId: Number.isInteger(data.tweet_id) ? data.tweet_id : null,
        eventId: event.id,
      });
      logger.info(`like notification for user ${data.tweet_author_id}`, { event_id: event.id });
    }
    // Any other event is not for us: ignore it.
  };
}

module.exports = { createEventHandler };
