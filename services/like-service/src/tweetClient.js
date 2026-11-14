// Asks tweet-service "what is tweet N?" over REST.
// Returns the tweet, or null if it does not exist. Throws if tweet-service cannot be reached.
function createTweetClient({ baseUrl, serviceName }) {
  return async function getTweet(id, requestId) {
    let lastError;
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const response = await fetch(`${baseUrl}/api/tweets/${id}`, {
          headers: { 'X-Caller': serviceName, 'X-Request-ID': requestId },
          signal: AbortSignal.timeout(3000),
        });
        if (response.status === 404) return null;
        if (!response.ok) throw new Error(`tweet-service answered ${response.status}`);
        return await response.json();
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError;
  };
}

module.exports = { createTweetClient };
