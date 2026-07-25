"""
Wallet & Billing Service — async SQLAlchemy repository.

IMPORTANT: WalletTransaction is IMMUTABLE.
The `create_transaction` method is the ONLY way to write transaction rows.
There is NO `update_transaction` method — intentionally.
"""

import uuid
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.marketplace_models import (
    Currency,
    StripeAccount,
    TransactionType,
    Wallet,
    WalletTransaction,
)
from services.wallet_billing_service.billing import (
    AMOUNT_PRECISION,
    apply_debit,
    apply_topup,
    assert_sufficient_balance,
)

logger = structlog.get_logger(__name__)


class WalletRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Wallet CRUD ────────────────────────────────────────────────────────
    async def create_wallet(
        self,
        user_id: uuid.UUID,
        preferred_currency: Currency = Currency.usd,
    ) -> Wallet:
        """Create a wallet with zero balance. Called on user signup."""
        wallet = Wallet(
            user_id=user_id,
            balance_usd=Decimal("0.000000"),
            balance_inr=Decimal("0.000000"),
            preferred_currency=preferred_currency,
        )
        self._session.add(wallet)
        await self._session.flush()
        await self._session.refresh(wallet)
        logger.info("wallet_created", wallet_id=str(wallet.id), user_id=str(user_id))
        return wallet

    async def get_by_user_id(self, user_id: uuid.UUID) -> Wallet | None:
        result = await self._session.execute(
            select(Wallet).where(Wallet.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, wallet_id: uuid.UUID) -> Wallet | None:
        result = await self._session.execute(
            select(Wallet).where(Wallet.id == wallet_id)
        )
        return result.scalar_one_or_none()

    # ── Immutable transaction append ───────────────────────────────────────
    async def create_transaction(
        self,
        wallet: Wallet,
        transaction_type: TransactionType,
        amount: Decimal,
        currency: Currency,
        usd_to_inr_rate: Decimal,
        stripe_payment_intent_id: str | None = None,
        stripe_transfer_id: str | None = None,
        listing_id: uuid.UUID | None = None,
        description: str | None = None,
    ) -> WalletTransaction:
        """
        Append an immutable transaction and update wallet balances atomically.

        For TOPUP: credits both USD and INR balances.
        For DEBIT: debits both (after balance check).
        Both amounts are stored in their canonical precision (6dp).
        """
        amount = amount.quantize(AMOUNT_PRECISION)

        if transaction_type == TransactionType.topup:
            new_usd, new_inr = apply_topup(
                wallet.balance_usd, wallet.balance_inr, amount, usd_to_inr_rate
            )
        elif transaction_type == TransactionType.debit:
            assert_sufficient_balance(
                wallet.balance_usd, wallet.balance_inr,
                amount, amount * usd_to_inr_rate,
                str(currency),
            )
            new_usd, new_inr = apply_debit(
                wallet.balance_usd, wallet.balance_inr, amount, usd_to_inr_rate
            )
        elif transaction_type in (TransactionType.refund, TransactionType.payout):
            # Refund: re-credit; Payout: debit for host payout
            if transaction_type == TransactionType.refund:
                new_usd, new_inr = apply_topup(
                    wallet.balance_usd, wallet.balance_inr, amount, usd_to_inr_rate
                )
            else:
                new_usd, new_inr = apply_debit(
                    wallet.balance_usd, wallet.balance_inr, amount, usd_to_inr_rate
                )
        else:
            raise ValueError(f"Unknown transaction_type: {transaction_type}")

        # Update wallet balances
        wallet.balance_usd = new_usd
        wallet.balance_inr = new_inr
        await self._session.flush()

        # Append immutable transaction row
        txn = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type=transaction_type,
            amount=amount,
            currency=currency,
            stripe_payment_intent_id=stripe_payment_intent_id,
            stripe_transfer_id=stripe_transfer_id,
            listing_id=listing_id,
            description=description,
            balance_after_usd=new_usd,
            balance_after_inr=new_inr,
        )
        self._session.add(txn)
        await self._session.flush()
        await self._session.refresh(txn)

        logger.info(
            "transaction_created",
            txn_id=str(txn.id),
            type=str(transaction_type),
            amount=float(amount),
            new_balance_usd=float(new_usd),
        )
        return txn

    # ── Transaction queries ────────────────────────────────────────────────
    async def get_transactions(
        self,
        wallet_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[WalletTransaction], int]:
        """Paginated transaction history (most recent first)."""
        offset = (page - 1) * page_size

        count_stmt = select(func.count()).select_from(WalletTransaction).where(
            WalletTransaction.wallet_id == wallet_id
        )
        total = (await self._session.execute(count_stmt)).scalar_one()

        rows_stmt = (
            select(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet_id)
            .order_by(WalletTransaction.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self._session.execute(rows_stmt)).scalars().all()
        return list(rows), total

    async def get_transaction_by_stripe_pi(
        self, payment_intent_id: str
    ) -> WalletTransaction | None:
        """Used to deduplicate Stripe webhook events."""
        result = await self._session.execute(
            select(WalletTransaction).where(
                WalletTransaction.stripe_payment_intent_id == payment_intent_id
            )
        )
        return result.scalar_one_or_none()


class StripeAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: uuid.UUID) -> StripeAccount | None:
        result = await self._session.execute(
            select(StripeAccount).where(StripeAccount.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: uuid.UUID,
        stripe_customer_id: str | None = None,
        stripe_connect_account_id: str | None = None,
    ) -> StripeAccount:
        acct = StripeAccount(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_connect_account_id=stripe_connect_account_id,
        )
        self._session.add(acct)
        await self._session.flush()
        await self._session.refresh(acct)
        return acct

    async def update_connect_account(
        self,
        stripe_account: StripeAccount,
        account_id: str,
        onboarding_complete: bool = False,
    ) -> StripeAccount:
        stripe_account.stripe_connect_account_id = account_id
        stripe_account.connect_onboarding_complete = onboarding_complete
        await self._session.flush()
        return stripe_account
