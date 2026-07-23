# Kynetic AI — REST & WebSocket API Specification

This document details the HTTP REST endpoints and WebSocket protocols exposed by the **Kynetic AI API Gateway (`:8000`)** and backend microservices.

---

## 1. Authentication & User Management (`/auth`)

### `POST /auth/register`
Creates a new developer or host user account.
- **Request Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "full_name": "Dev User",
    "role": "developer",
    "phone_number": "+919876543210"
  }
  ```
- **Response `201 Created`**:
  ```json
  {
    "id": "u_991823",
    "email": "user@example.com",
    "role": "developer",
    "created_at": "2026-07-24T00:00:00Z"
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
        "listing_id": "lst_8829",
        "host_id": "h_102",
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

## 3. Provisioning & Instance Management (`/provisioning`)

### `POST /provisioning/instances`
Spins up a Firecracker MicroVM / container instance on an attested host.
- **Request Body**:
  ```json
  {
    "listing_id": "lst_8829",
    "app_template": "comfyui",
    "ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI..."
  }
  ```
- **Response `202 Accepted`**:
  ```json
  {
    "instance_id": "inst_44910",
    "status": "provisioning",
    "estimated_seconds": 12
  }
  ```

### `GET /provisioning/instances/{instance_id}`
Fetches instance status, connection info, and execution certificate.
- **Response `200 OK`**:
  ```json
  {
    "instance_id": "inst_44910",
    "status": "running",
    "ssh_command": "ssh -i ~/.ssh/kynetic_id root@relay.kynetic.ai -p 22049",
    "web_ui_url": "https://inst-44910.kynetic.app",
    "attestation_certified": true
  }
  ```

---

## 4. Wallet & Billing (`/billing`)

### `POST /billing/deposit/razorpay`
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
    "recommended_listing_id": "lst_8829",
    "reasoning": "Selected RTX 4090 with 24GB VRAM ($0.45/hr) matching 98.4 reputation score."
  }
  ```
