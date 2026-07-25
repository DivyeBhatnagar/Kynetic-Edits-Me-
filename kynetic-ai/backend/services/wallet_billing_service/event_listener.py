"""
Wallet & Billing Service — Redis event listener.

Subscribes to the `kynetic:events:user_created` pub/sub channel
and auto-creates a Wallet + Stripe Customer for each new user.

Runs as a daemon thread started in main.py on application startup.
This decouples the Auth Service from the Wallet Service — no direct
HTTP call from auth → wallet at signup time.

Event format (JSON):
  {
    "user_id": "<uuid>",
    "email": "<email>",
    "role": "developer" | "host"
  }
"""

import asyncio
import json
import threading
import uuid
from decimal import Decimal

import redis
import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from libs.db_models.marketplace_models import Currency, StripeAccount, Wallet
from services.wallet_billing_service import stripe_client as sc
from services.wallet_billing_service.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# Initialize Stripe
sc.init_stripe(settings.stripe_secret_key)


def _get_sync_session() -> Session:
    sync_url = settings.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    return Session(engine)


def _handle_user_created(event_data: dict) -> None:
    """
    Create wallet + Stripe customer for a newly registered user.
    Idempotent: if wallet already exists, do nothing.
    """
    user_id_str = event_data.get("user_id")
    email = event_data.get("email", "")

    if not user_id_str:
        logger.warning("user_created_event_missing_user_id", data=event_data)
        return

    user_id = uuid.UUID(user_id_str)

    with _get_sync_session() as session:
        # Check idempotency
        existing = session.get(Wallet, user_id)  # type: ignore[arg-type]
        if existing:
            logger.debug("wallet_already_exists_skip", user_id=str(user_id))
            return

        # Create Stripe Customer (sync SDK call)
        try:
            customer = sc.create_customer(email=email, user_id=str(user_id))
            stripe_customer_id = customer.id
        except Exception as exc:
            logger.error("stripe_customer_creation_failed", error=str(exc))
            stripe_customer_id = None  # Wallet still created, Stripe can be retried

        # Create wallet (₹0 / $0)
        wallet = Wallet(
            user_id=user_id,
            balance_usd=Decimal("0.000000"),
            balance_inr=Decimal("0.000000"),
            preferred_currency=Currency.usd,
        )
        session.add(wallet)

        # Create Stripe account record
        stripe_acct = StripeAccount(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
        )
        session.add(stripe_acct)

        session.commit()
        logger.info(
            "wallet_auto_created",
            user_id=str(user_id),
            stripe_customer_id=stripe_customer_id,
        )


def start_event_listener() -> threading.Thread:
    """
    Start the Redis pub/sub listener in a background daemon thread.
    Call this from application startup.
    """

    def _listen():
        try:
            r = redis.from_url(settings.redis_url, decode_responses=True)
            pubsub = r.pubsub()
            pubsub.subscribe(settings.user_created_channel)
            logger.info(
                "wallet_event_listener_started",
                channel=settings.user_created_channel,
            )

            for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    _handle_user_created(data)
                except Exception as exc:
                    logger.error("user_created_event_error", error=str(exc))

        except Exception as exc:
            logger.error("wallet_event_listener_crashed", error=str(exc))

    t = threading.Thread(target=_listen, daemon=True, name="wallet_event_listener")
    t.start()
    return t
