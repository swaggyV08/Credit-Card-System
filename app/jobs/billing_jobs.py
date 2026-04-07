"""
Billing Scheduled Jobs

Uses asyncio-native background tasks to run daily billing operations:
  • 00:01 UTC — Statement generation for the previous day's cycle
  • 00:05 UTC — Late fee application for overdue statements

No external scheduler library required — fully compliant with the mandated
tech stack (Python stdlib asyncio only).

The scheduler is started from the FastAPI lifespan context in main.py.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

logger = logging.getLogger("zbanque.jobs")


# ---------------------------------------------------------------------------
# JOB FUNCTIONS (sync — run in thread pool via asyncio.to_thread)
# ---------------------------------------------------------------------------

def run_daily_statement_generation() -> None:
    """Generate billing statements for the previous day's cycle."""
    from app.db.session import SessionLocal
    from app.services.billing_service import BillingService

    logger.info("Scheduled job: Starting daily statement generation")
    db = SessionLocal()
    try:
        yesterday = date.today() - timedelta(days=1)
        results = BillingService.generate_statements(db, cycle_date=yesterday)
        logger.info(
            "Statement generation complete: %d statements generated",
            len(results),
        )
    except Exception:
        logger.exception("Statement generation job failed")
        db.rollback()
    finally:
        db.close()


def run_daily_late_fee_application() -> None:
    """Apply late fees to overdue statements."""
    from app.db.session import SessionLocal
    from app.services.billing_service import BillingService

    logger.info("Scheduled job: Starting daily late fee application")
    db = SessionLocal()
    try:
        results = BillingService.apply_late_fees(db, late_fee_amount=Decimal("500.00"))
        logger.info(
            "Late fee application complete: %d fees applied",
            len(results),
        )
    except Exception:
        logger.exception("Late fee application job failed")
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# ASYNCIO SCHEDULER
# ---------------------------------------------------------------------------

async def _run_at_utc(hour: int, minute: int, job_fn) -> None:
    """
    Infinite loop that fires job_fn once per day at the given UTC time.
    Uses asyncio.sleep so it yields the event loop while waiting.
    """
    while True:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logger.info(
            "Next run of %s in %.0f seconds (at %s UTC)",
            job_fn.__name__,
            wait_seconds,
            target.strftime("%H:%M"),
        )
        await asyncio.sleep(wait_seconds)
        try:
            await asyncio.to_thread(job_fn)
        except Exception:
            logger.exception("Scheduled job raised an unhandled error: %s", job_fn.__name__)


async def start_billing_scheduler() -> None:
    """
    Create asyncio background tasks for each billing job.
    Call this inside the FastAPI lifespan context manager.
    """
    asyncio.create_task(
        _run_at_utc(0, 1, run_daily_statement_generation),
        name="daily_statement_generation",
    )
    asyncio.create_task(
        _run_at_utc(0, 5, run_daily_late_fee_application),
        name="daily_late_fee_application",
    )
    logger.info(
        "Billing scheduler started with 2 daily asyncio tasks "
        "(statement: 00:01 UTC, late-fees: 00:05 UTC)"
    )
