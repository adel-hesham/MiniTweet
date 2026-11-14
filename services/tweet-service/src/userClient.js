// Asks user-service "who is user N?" over REST.
// Returns the user, or null if the user does not exist. Throws if user-service cannot be reached.
function createUserClient({ baseUrl, serviceName }) {
  return async function getUser(id, requestId) {
    let lastError;
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const response = await fetch(`${baseUrl}/api/users/${id}`, {
          headers: { 'X-Caller': serviceName, 'X-Request-ID': requestId },
          signal: AbortSignal.timeout(3000),
        });
        if (response.status === 404) return null;
        if (!response.ok) throw new Error(`user-service answered ${response.status}`);
        return await response.json();
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError;
  };
}

module.exports = { createUserClient };
