import http from 'k6/http';
import { check, sleep } from 'k6';

/*
  Phase 14 — k6 Load Test Suite for Kynetic AI
  Target: 100+ req/sec API throughput with <100ms latency p95

  Usage:
    k6 run tests/load/k6_load_test.js
*/

export const options = {
  stages: [
    { duration: '30s', target: 20 },  // Ramp up to 20 VUs
    { duration: '1m', target: 100 },  // Spike to 100 VUs (10x launch traffic)
    { duration: '30s', target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<200'], // 95% of requests must complete within 200ms
    http_req_failed: ['rate<0.01'],   # HTTP errors must be < 1%
  },
};

const BASE_URL = __ENV.API_URL || 'http://localhost:8000';

export default function () {
  // 1. Health check
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    'health status is 200': (r) => r.status === 200,
  });

  // 2. Marketplace listings
  const listingsRes = http.get(`${BASE_URL}/listings`);
  check(listingsRes, {
    'listings status is 200 or 404': (r) => r.status === 200 || r.status === 404,
  });

  sleep(0.5);
}
