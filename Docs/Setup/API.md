# Kynetic AI — REST & WebSocket API Specification

This document details the HTTP REST endpoints and WebSocket protocols exposed by the **Kynetic AI API Gateway (`:8000`)** and backend microservices.

---

## 1. Authentication & User Management (`/auth`)

### `POST /auth/signup`
Creates a new developer or host user account.
- **Request Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "role": "developer",
    "phone_number": "+919876543210"
  }
  ```
- **Response `201 Created`**:
  ```json
  {
    "id": "3b40dbb3-be8f-425a-9d35-27641f38627f",
    "email": "user@example.com",
    "role": "developer",
    "is_active": true
  }
  ```

### `POST /auth/login`
Authenticates a user and issues JWT access and refresh tokens.
- **Request Body**: `OAuth2PasswordRequestForm` (`username`, `password`)
- **Response `200 OK`**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "token_type": "bearer",
    "expires_in": 3600
  }
  ```

---

## 2. Marketplace & Compute Search (`/marketplace`)

### `POST /marketplace/search`
Searches compute listings by intent or explicit hardware requirements.
- **Request Body**:
  ```json
  {
    "gpu_models": ["RTX 4090", "A100"],
    "min_vram_gb": 24,
    "min_ram_gb": 32,
    "max_price_usd_per_hr": "0.60"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "listings": [
      {
        "listing_id": "adfe314c-cd5d-4979-8879-596b4b8885b3",
        "host_id": "794729a5-b3f2-42a6-b2aa-f95f6d23b403",
        "gpu_model": "NVIDIA GeForce RTX 4090",
        "vram_gb": 24,
        "hourly_price_usd": "0.45",
        "reputation_score": 98.4,
        "security_tier": "standard_tier"
      }
    ],
    "external_fallbacks": [
      {
        "provider": "RunPod",
        "gpu_model": "RTX 4090",
        "hourly_price_usd": "0.69",
        "direct_link": "https://runpod.io/gpus/rtx4090"
      }
    ]
  }
  ```

---

## 3. Provisioning & Instance Management (`/v1/instances`)

### `POST /v1/instances`
Pre-flight validates and launches a Firecracker MicroVM / container instance.
- **Request Body (`InstanceCreateRequest`)**:
  ```json
  {
    "listing_id": "adfe314c-cd5d-4979-8879-596b4b8885b3",
    "requested_hours": 1.0,
    "template_id": "31f8cb41-0000-0000-0000-000000000000"
  }
  ```
- **Response `201 Created` (`InstanceResponse`)**:
  ```json
  {
    "id": "e85fee82-b0cc-4bb5-bf29-ef7b7a5dd53b",
    "developer_id": "3b40dbb3-be8f-425a-9d35-27641f38627f",
    "listing_id": "adfe314c-cd5d-4979-8879-596b4b8885b3",
    "host_id": "794729a5-b3f2-42a6-b2aa-f95f6d23b403",
    "status": "pending",
    "hold_amount": 1.0,
    "price_per_second_usd": 0.000277,
    "created_at": "2026-07-24T23:59:00Z"
  }
  ```
- **Validation Rejection Error Codes (Phase 27)**:
  - `402 Payment Required`: `{"detail": "Wallet balance insufficient to cover 1.0 hours ($1.00 USD)"}`
  - `403 Forbidden`: `{"detail": "Cannot launch instance for another developer"}`
  - `404 Not Found`: `{"detail": "Listing not found"}`
  - `409 Conflict`: `{"detail": "Host heartbeat is stale (last seen >60s ago)"}`

### `GET /v1/instances/{id}`
Fetches instance details and execution status.
- **Response `200 OK` (`InstanceResponse`)**

### `GET /v1/instances`
Lists instances owned by developer with status filtering and pagination.
- **Query Params**: `status` (optional), `skip` (default 0), `limit` (default 20).
- **Response `200 OK` (`InstanceListResponse`)**:
  ```json
  {
    "items": [...],
    "total": 1,
    "skip": 0,
    "limit": 20
  }
  ```

### `POST /v1/instances/{id}/stop`
Suspends a running Firecracker MicroVM.
- **Response `202 Accepted` (`InstanceActionResponse`)**:
  ```json
  {
    "instance_id": "e85fee82-b0cc-4bb5-bf29-ef7b7a5dd53b",
    "status": "stopping",
    "message": "Stop initiated"
  }
  ```

### `POST /v1/instances/{id}/terminate`
Destroys MicroVM/container, shreds NVMe storage, and releases hold.
- **Response `202 Accepted` (`InstanceActionResponse`)**:
  ```json
  {
    "instance_id": "e85fee82-b0cc-4bb5-bf29-ef7b7a5dd53b",
    "status": "terminated",
    "message": "Termination initiated"
  }
  ```

### `GET /v1/instances/{id}/connection`
Fetches ready-to-paste SSH command and temporary connection details.
- **Response `200 OK` (`InstanceConnectionResponse`)**:
  ```json
  {
    "instance_id": "e85fee82-b0cc-4bb5-bf29-ef7b7a5dd53b",
    "ssh_command": "ssh -i kynetic_key.pem kynetic@10.42.1.50",
    "ssh_host": "10.42.1.50",
    "ssh_port": 22,
    "web_ui_url": "https://inst-e85fee82.kynetic.app"
  }
  ```

---

## 4. Wallet & Billing (`/billing`)

### `POST /wallet/topup/upi`
Initiates a UPI / Razorpay INR deposit.
- **Request Body**: `{"amount_inr": "1000.00"}`
- **Response `200 OK`**:
  ```json
  {
    "order_id": "order_NzX19283",
    "amount_paise": 100000,
    "currency": "INR",
    "razorpay_key_id": "rzp_test_..."
  }
  ```

---

## 5. AI Copilot WebSocket Protocol (`ws://.../copilot/ws`)

- **Connection**: `ws://localhost:8005/copilot/ws?token=<JWT>`
- **Client Message**:
  ```json
  {"message": "I need to fine-tune Llama 3 8B with Unsloth under $0.50/hr"}
  ```
- **Server Response Stream**:
  ```json
  {
    "type": "recommendation",
    "intent": "fine_tune_llama3_8b",
    "recommended_listing_id": "adfe314c-cd5d-4979-8879-596b4b8885b3",
    "estimated_cost_usd": "0.45",
    "estimated_hours": 2.5
  }
  ```
