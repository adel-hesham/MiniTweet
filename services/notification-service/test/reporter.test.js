const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { EventEmitter } = require('node:events');
const { reportMiddleware } = require('../src/reporter');

// A tiny stand-in for monitor-service that remembers what it receives.
async function startFakeMonitor() {
  const received = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      received.push({ url: req.url, record: JSON.parse(body) });
      res.end('ok');
    });
  });
  await new Promise((resolve) => server.listen(0, resolve));
  return {
    received,
    url: `http://127.0.0.1:${server.address().port}`,
    close: () => new Promise((resolve) => { server.close(resolve); server.closeAllConnections(); }),
  };
}

async function waitFor(condition, ms = 1500) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (condition()) return true;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  return false;
}

function fakeResponse(status = 200, requestId = 'abc123') {
  const res = new EventEmitter();
  res.statusCode = status;
  res.getHeader = (name) => (name === 'x-request-id' ? requestId : undefined);
  return res;
}

test('a finished request is reported to monitor-service', async () => {
  const monitor = await startFakeMonitor();
  process.env.MONITOR_URL = monitor.url;
  try {
    const middleware = reportMiddleware({ serviceName: 'tweet-service' });
    const req = { originalUrl: '/api/tweets?limit=5', method: 'GET', headers: { 'x-caller': 'like-service' } };
    const res = fakeResponse(200);
    let nextCalled = false;
    middleware(req, res, () => { nextCalled = true; });
    assert.equal(nextCalled, true);
    res.emit('finish');

    assert.equal(await waitFor(() => monitor.received.length === 1), true);
    assert.equal(monitor.received[0].url, '/api/monitor/ingest/request');
    const record = monitor.received[0].record;
    assert.equal(record.service, 'tweet-service');
    assert.equal(record.caller, 'like-service');
    assert.equal(record.method, 'GET');
    assert.equal(record.path, '/api/tweets');
    assert.equal(record.status, 200);
    assert.equal(record.request_id, 'abc123');
    assert.equal(typeof record.duration_ms, 'number');
  } finally {
    delete process.env.MONITOR_URL;
    await monitor.close();
  }
});

test('requests from the browser are reported with caller "browser"', async () => {
  const monitor = await startFakeMonitor();
  process.env.MONITOR_URL = monitor.url;
  try {
    const middleware = reportMiddleware({ serviceName: 'tweet-service' });
    const res = fakeResponse(201);
    middleware({ originalUrl: '/api/tweets', method: 'POST', headers: {} }, res, () => {});
    res.emit('finish');
    assert.equal(await waitFor(() => monitor.received.length === 1), true);
    assert.equal(monitor.received[0].record.caller, 'browser');
  } finally {
    delete process.env.MONITOR_URL;
    await monitor.close();
  }
});

test('health and ready checks are not reported', async () => {
  const monitor = await startFakeMonitor();
  process.env.MONITOR_URL = monitor.url;
  try {
    const middleware = reportMiddleware({ serviceName: 'tweet-service' });
    for (const path of ['/health', '/ready', '/api/tweets/health']) {
      const res = fakeResponse(200);
      middleware({ originalUrl: path, method: 'GET', headers: {} }, res, () => {});
      res.emit('finish');
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
    assert.equal(monitor.received.length, 0);
  } finally {
    delete process.env.MONITOR_URL;
    await monitor.close();
  }
});

test('without MONITOR_URL nothing is sent and the request carries on', () => {
  delete process.env.MONITOR_URL;
  const middleware = reportMiddleware({ serviceName: 'tweet-service' });
  const res = fakeResponse(200);
  let nextCalled = false;
  middleware({ originalUrl: '/api/tweets', method: 'GET', headers: {} }, res, () => { nextCalled = true; });
  assert.equal(nextCalled, true);
  assert.equal(res.listenerCount('finish'), 0);
});

test('if monitor-service is down the request is not affected', async () => {
  process.env.MONITOR_URL = 'http://127.0.0.1:9';
  try {
    const middleware = reportMiddleware({ serviceName: 'tweet-service' });
    const res = fakeResponse(200);
    middleware({ originalUrl: '/api/tweets', method: 'GET', headers: {} }, res, () => {});
    res.emit('finish');
    await new Promise((resolve) => setTimeout(resolve, 200)); // no crash, no unhandled rejection
  } finally {
    delete process.env.MONITOR_URL;
  }
});
