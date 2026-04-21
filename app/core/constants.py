"""
Application-wide constants. No magic numbers in any module.
"""

# ── Password ──────────────────────────────────────────────────────────
MIN_PASSWORD_LENGTH = 12

# ── OTP ───────────────────────────────────────────────────────────────
OTP_TTL_MINUTES = 10
OTP_LENGTH = 6

# ── Password Reset Token ─────────────────────────────────────────────
RESET_TOKEN_TTL_MINUTES = 15

# ── File Upload ───────────────────────────────────────────────────────
MAX_FILE_SIZE_BYTES = 5_242_880  # 5 MB
ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}

# ── KYC Document Regex Patterns ───────────────────────────────────────
DOC_PATTERNS = {
    "PAN": r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$",
    "AADHAAR": r"^\d{12}$",
    "PASSPORT": r"^[A-Z]{1}[0-9]{7}$",
    "VOTER_ID": r"^[A-Z]{3}[0-9]{7}$",
    "DRIVING_LICENSE": r"^[A-Z0-9]{10,16}$",
}

DOC_FORMAT_DESCRIPTIONS = {
    "PAN": "ABCDE1234F (5 letters, 4 digits, 1 letter)",
    "AADHAAR": "12-digit number",
    "PASSPORT": "1 letter followed by 7 digits",
    "VOTER_ID": "3 letters followed by 7 digits",
    "DRIVING_LICENSE": "10-16 alphanumeric characters",
}

# ── Phone ─────────────────────────────────────────────────────────────
COUNTRY_CODE_MIN_DIGITS = 1
COUNTRY_CODE_MAX_DIGITS = 4
PHONE_MIN_DIGITS = 7
PHONE_MAX_DIGITS = 15

# ── Dispute ───────────────────────────────────────────────────────────
DISPUTE_WINDOW_DAYS = 120

# ── Velocity (window sizes in seconds) ──────────────────────────────────
VELOCITY_WINDOW_1M = 60
VELOCITY_WINDOW_10M = 600
VELOCITY_WINDOW_1H = 3600
VELOCITY_WINDOW_24H = 86400

# ── API ───────────────────────────────────────────────────────────────
API_VERSION = "v1"
