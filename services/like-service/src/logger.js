// One JSON object per line, same field names in every service (see docs/contracts.md).
function createLogger(service, requestId = '-') {
  function write(level, message, fields) {
    if (process.env.LOG_SILENT === '1') return;
    const entry = {
      timestamp: new Date().toISOString(),
      level,
      service,
      message,
      request_id: requestId,
      ...fields,
    };
    process.stdout.write(JSON.stringify(entry) + '\n');
  }

  return {
    info: (message, fields = {}) => write('INFO', message, fields),
    warn: (message, fields = {}) => write('WARNING', message, fields),
    error: (message, fields = {}) => write('ERROR', message, fields),
  };
}

module.exports = { createLogger };
