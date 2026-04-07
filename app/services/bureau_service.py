import asyncio
from datetime import datetime, timezone, timedelta
from uuid import UUID
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.models.bureau import BureauScore
from app.models.enums import BureauRiskBand, ScoreTrigger
from app.models.auth import User
from app.admin.models.card_issuance import CreditAccount, Card
from app.models.billing import Payment
from app.models.card_management import CCMCardTransaction
from app.models.transactions.disputes import Dispute
from app.core.exceptions import AppError

def classify_band(score: int) -> BureauRiskBand:
    """Maps a raw score integer [300, 900] to the corresponding risk band."""
    if score < 550: return BureauRiskBand.POOR
    if score < 650: return BureauRiskBand.FAIR
    if score < 750: return BureauRiskBand.GOOD
    if score < 850: return BureauRiskBand.VERY_GOOD
    return BureauRiskBand.EXCELLENT

def _compute_payment_history(on_time_count: int, late_count: int, missed_count: int, has_3_consecutive_misses: bool) -> int:
    if has_3_consecutive_misses:
        return 0
    total_payments = on_time_count + late_count + missed_count
    if total_payments == 0:
        return 175
    on_time_ratio = on_time_count / total_payments
    base_score = round(on_time_ratio * 350)
    late_deduction = min(late_count * 15, 105)
    missed_deduction = min(missed_count * 35, 175)
    return max(0, base_score - late_deduction - missed_deduction)

def _compute_utilisation(utilisation_pct: float) -> int:
    u = utilisation_pct
    if u < 10: return 300
    if u < 20: return 270
    if u < 30: return 240
    if u < 40: return 200
    if u < 50: return 160
    if u < 60: return 120
    if u < 75: return 80
    if u < 90: return 40
    return 0

def _compute_credit_history(created_at: datetime) -> int:
    account_age_days = (datetime.now(timezone.utc) - created_at).days
    if account_age_days < 180: return 0
    if account_age_days < 365: return 30
    if account_age_days < 730: return 70
    if account_age_days < 1095: return 100
    if account_age_days < 1825: return 125
    return 150

def _compute_transaction_behaviour(total_transactions_90d: int, disputes_90d: int, reversed_90d: int) -> int:
    if total_transactions_90d == 0: volume_score = 40
    elif total_transactions_90d < 5: volume_score = 60
    elif total_transactions_90d < 20: volume_score = 90
    else: volume_score = 120
    dispute_deduction = min(disputes_90d * 20, 60)
    reversal_deduction = min(reversed_90d * 10, 40)
    return max(0, volume_score - dispute_deduction - reversal_deduction)

def _compute_derogatory(chargebacks_total: int, over_limit_mark: int) -> int:
    total_marks = chargebacks_total + over_limit_mark
    if total_marks == 0: return 80
    if total_marks == 1: return 40
    if total_marks == 2: return 15
    return 0

async def _fetch_payment_counts(account_id: UUID, db: AsyncSession) -> dict:
    stmt = select(Payment.status).where(Payment.credit_account_id == account_id).order_by(Payment.payment_date.asc())
    result = await db.execute(stmt)
    statuses = [row[0] for row in result.all()]
    on_time = sum(1 for s in statuses if s == "ON_TIME" or s == "POSTED")
    late = sum(1 for s in statuses if s == "LATE")
    missed = sum(1 for s in statuses if s == "MISSED" or s == "FAILED")

    consecutive_misses = 0
    has_3 = False
    for s in statuses:
        if s == "MISSED" or s == "FAILED":
            consecutive_misses += 1
            if consecutive_misses >= 3:
                has_3 = True
                break
        else:
            consecutive_misses = 0

    return {
        "on_time_count": on_time,
        "late_count": late,
        "missed_count": missed,
        "has_3_consecutive_misses": has_3
    }

async def _fetch_utilisation(account_id: UUID, db: AsyncSession) -> dict:
    stmt = select(CreditAccount.credit_limit, CreditAccount.outstanding_amount).where(CreditAccount.id == account_id)
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        return {"utilisation_pct": 0.0, "over_limit_mark": 0}
    credit_limit = float(row[0] or 0)
    outstanding_amount = float(row[1] or 0)
    if credit_limit == 0:
        util_pct = 0.0
    else:
        util_pct = (outstanding_amount / credit_limit) * 100
    
    over_limit = 1 if outstanding_amount > credit_limit else 0
    return {"utilisation_pct": util_pct, "over_limit_mark": over_limit}

async def _fetch_transaction_data(user_id: UUID, db: AsyncSession) -> dict:
    stmt_cards = select(Card.id).join(CreditAccount, CreditAccount.id == Card.credit_account_id).where(CreditAccount.user_id == user_id)
    card_ids_res = await db.execute(stmt_cards)
    card_ids = [row[0] for row in card_ids_res.all()]
    if not card_ids:
        return {"total_transactions_90d": 0, "disputes_90d": 0, "reversed_90d": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    stmt_tx = select(CCMCardTransaction.status).where(
        and_(
            CCMCardTransaction.card_id.in_(card_ids),
            CCMCardTransaction.transaction_date >= cutoff
        )
    )
    res_tx = await db.execute(stmt_tx)
    statuses = [row[0] for row in res_tx.all()]
    return {
        "total_transactions_90d": len(statuses),
        "disputes_90d": sum(1 for s in statuses if s == "DISPUTED"),
        "reversed_90d": sum(1 for s in statuses if s == "REVERSED")
    }

async def _fetch_derogatory_data(user_id: UUID, db: AsyncSession) -> dict:
    stmt_cards = select(Card.id).join(CreditAccount, CreditAccount.id == Card.credit_account_id).where(CreditAccount.user_id == user_id)
    card_ids_res = await db.execute(stmt_cards)
    card_ids = [row[0] for row in card_ids_res.all()]
    if not card_ids:
        return {"chargebacks_total": 0}

    stmt_disp = select(func.count(Dispute.id)).where(
        and_(
            Dispute.card_id.in_(card_ids),
            Dispute.resolution == "RESOLVED_LOST"
        )
    )
    res_disp = await db.execute(stmt_disp)
    return {"chargebacks_total": res_disp.scalar() or 0}

async def _persist_score(user_id: UUID, score: int, risk_band: BureauRiskBand, trigger_event: ScoreTrigger, trigger_ref_id: UUID | None, computed_by: UUID | None, factor_scores: dict, factor_inputs: dict, db: AsyncSession) -> BureauScore:
    bs = BureauScore(
        user_id=user_id,
        score=score,
        risk_band=risk_band,
        trigger_event=trigger_event,
        trigger_ref_id=trigger_ref_id,
        computed_by=computed_by,
        payment_history_score=factor_scores.get("payment_history_score", 0),
        utilisation_score=factor_scores.get("utilisation_score", 0),
        credit_history_score=factor_scores.get("credit_history_score", 0),
        transaction_behaviour_score=factor_scores.get("transaction_behaviour_score", 0),
        derogatory_score=factor_scores.get("derogatory_score", 0),
        on_time_payment_count=factor_inputs.get("on_time_payment_count", 0),
        late_payment_count=factor_inputs.get("late_payment_count", 0),
        missed_payment_count=factor_inputs.get("missed_payment_count", 0),
        current_utilisation_pct=Decimal(str(factor_inputs.get("current_utilisation_pct", 0))),
        account_age_days=factor_inputs.get("account_age_days", 0),
        total_transactions_90d=factor_inputs.get("total_transactions_90d", 0),
        disputes_90d=factor_inputs.get("disputes_90d", 0),
        chargebacks_total=factor_inputs.get("chargebacks_total", 0),
        computed_at=datetime.now(timezone.utc)
    )
    db.add(bs)
    await db.commit()
    await db.refresh(bs)
    return bs

async def compute_bureau_score(user_id: UUID, trigger_event: ScoreTrigger, trigger_ref_id: UUID | None, computed_by: UUID | None, db: AsyncSession) -> BureauScore:
    user_res = await db.execute(select(User).where(User.id == user_id))
    user = user_res.scalar()
    if not user:
        raise AppError(code="USER_NOT_FOUND", message="No user account found for the given user_id.", http_status=404)

    acc_res = await db.execute(select(CreditAccount).where(CreditAccount.user_id == user_id))
    account = acc_res.scalar()
    if not account:
        return await _persist_score(
            user_id=user_id, score=300, risk_band=BureauRiskBand.POOR, trigger_event=trigger_event,
            trigger_ref_id=trigger_ref_id, computed_by=computed_by, factor_scores={}, factor_inputs={}, db=db
        )

    payment_counts, util_data, txn_data, derog_data = await asyncio.gather(
        _fetch_payment_counts(account.id, db),
        _fetch_utilisation(account.id, db),
        _fetch_transaction_data(user_id, db),
        _fetch_derogatory_data(user_id, db)
    )

    f1 = _compute_payment_history(payment_counts["on_time_count"], payment_counts["late_count"], payment_counts["missed_count"], payment_counts["has_3_consecutive_misses"])
    f2 = _compute_utilisation(util_data["utilisation_pct"])
    f3 = _compute_credit_history(user.created_at)
    f4 = _compute_transaction_behaviour(txn_data["total_transactions_90d"], txn_data["disputes_90d"], txn_data["reversed_90d"])
    f5 = _compute_derogatory(derog_data["chargebacks_total"], util_data["over_limit_mark"])

    raw_total = f1 + f2 + f3 + f4 + f5
    score = round(300 + (raw_total / 1000) * 600)
    score = max(300, min(900, score))

    return await _persist_score(
        user_id=user_id, score=score, risk_band=classify_band(score), trigger_event=trigger_event,
        trigger_ref_id=trigger_ref_id, computed_by=computed_by,
        factor_scores={"payment_history_score": f1, "utilisation_score": f2, "credit_history_score": f3, "transaction_behaviour_score": f4, "derogatory_score": f5},
        factor_inputs={
            "on_time_payment_count": payment_counts["on_time_count"],
            "late_payment_count": payment_counts["late_count"],
            "missed_payment_count": payment_counts["missed_count"],
            "current_utilisation_pct": util_data["utilisation_pct"],
            "account_age_days": (datetime.now(timezone.utc) - user.created_at).days,
            "total_transactions_90d": txn_data["total_transactions_90d"],
            "disputes_90d": txn_data["disputes_90d"],
            "chargebacks_total": derog_data["chargebacks_total"]
        },
        db=db
    )
