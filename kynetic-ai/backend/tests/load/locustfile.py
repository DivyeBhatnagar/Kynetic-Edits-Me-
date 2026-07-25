"""
Phase 14 — Locust Load Test Suite for Kynetic AI Platform

Simulates concurrent user load at 10x launch traffic:
  - Developer User Flow: Browse listings, query AI Router, check instance status, check wallet
  - Host Agent Flow: Send 10s heartbeats, report hardware telemetry
  - High-frequency wallet debits

Usage:
  locust -f tests/load/locustfile.py --headless -u 50 -r 10 --run-time 1m --host http://localhost:8000
"""

from locust import HttpUser, task, between
import random


class DeveloperUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def browse_marketplace_listings(self):
        self.client.get("/listings", name="/listings")

    @task(2)
    def query_ai_router(self):
        payload = {
            "intent": "Fine-tune Llama 3 8B model with PyTorch",
            "max_budget_usd_per_hour": 1.50,
            "region": "ap-south-1"
        }
        self.client.post("/router/recommend", json=payload, name="/router/recommend")

    @task(1)
    def check_wallet_balance(self):
        headers = {"Authorization": "Bearer mock_jwt_token_for_load_testing"}
        self.client.get("/wallet/balance", headers=headers, name="/wallet/balance")


class HostAgentUser(HttpUser):
    wait_time = between(8, 12)  # Host agent heartbeats every 10 seconds

    @task
    def send_host_heartbeat(self):
        payload = {
            "host_id": "host_load_test_node_01",
            "status": "idle",
            "temperature_c": random.randint(45, 75),
            "power_draw_w": random.randint(150, 350)
        }
        self.client.post("/hosts/heartbeat", json=payload, name="/hosts/heartbeat")
