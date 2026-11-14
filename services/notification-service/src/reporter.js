// Tells monitor-service about every request this service handles (for the live dashboard).
// Fire and forget: if MONITOR_URL is not set or monitor-service is down, nothing happens.
function reportMiddleware({ serviceName }) {
  const monitorUrl = process.env.MONITOR_URL || '';

  return (req, res, next) => {
    if (!monitorUrl) return next();
    const started = process.hrtime.bigint();
    res.on('finish', () => {
      const path = req.originalUrl.split('?')[0];
      if (path.endsWith('/health') || path.endsWith('/ready')) return;
      const record = {
        time: new Date().toISOString(),
        service: serviceName,
        caller: req.headers['x-caller'] || 'browser',
        method: req.method,
        path,
        status: res.statusCode,
        duration_ms: Math.round(Number(process.hrtime.bigint() - started) / 1e5) / 10,
        request_id: String(res.getHeader('x-request-id') || req.headers['x-request-id'] || '-'),
      };
      fetch(`${monitorUrl}/api/monitor/ingest/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(record),
        signal: AbortSignal.timeout(1000),
      }).catch(() => {});
    });
    return next();
  };
}

module.exports = { reportMiddleware };
