from app.models.enums import BureauRiskBand

def classify_band(score: int) -> BureauRiskBand:
    if score < 550: return BureauRiskBand.POOR
    if score < 650: return BureauRiskBand.FAIR
    if score < 750: return BureauRiskBand.GOOD
    if score < 850: return BureauRiskBand.VERY_GOOD
    return BureauRiskBand.EXCELLENT

def _compute_payment_history(on_time, late, missed, consecutive_missed):
    if consecutive_missed: return 0
    if on_time == 0 and late == 0 and missed == 0: return 175
    base = (on_time / (on_time + late + missed)) * 350
    return max(0, base - (late * 15) - (missed * 35))

def _compute_utilisation(u_pct):
    if u_pct >= 90: return 0
    if u_pct < 10: return 300
    return max(0, 300 - (u_pct * 3))

def _compute_credit_history(created_at):
    from datetime import datetime, timezone
    days = (datetime.now(timezone.utc) - created_at).days
    if days < 180: return 0
    if days > 1825: return 150
    return min(150, (days / 1825) * 150)

def _compute_transaction_behaviour(vol, disputes, chargebacks):
    base = min(120, vol * 6)
    return max(0, base - (disputes * 20) - (chargebacks * 50))

def _compute_derogatory(marks, history):
    if marks + history >= 3: return 0
    return max(0, 80 - (marks * 30) - (history * 20))
