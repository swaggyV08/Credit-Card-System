# ZBANQUe Credit Card Management System

## Overview
**ZBANQUe** is a production-grade Credit Card Management System architected for reliability, security, and developer ergonomics. Built with the modern Python ecosystem, it leverages asynchronous patterns and type-safe data modeling to handle the entire credit card lifecycle—from complex underwriting and KYC verification to real-time transaction processing, billing statements, and payment allocation.

## Architecture & Design Patterns
The system is built on a **Layered Architecture** with strict separation of concerns, ensuring high maintainability and testability:

- **API Layer (Controller):** FastAPI routers handling request orchestration, serialization, and OpenAPI documentation.
- **Service Layer:** Houses the core business logic, domain services (e.g., Underwriting Engine, OTP Dispatcher, Billing Service, Transaction Service), and transactional workflows.
- **Data Layer (Repository):** Utilizes **SQLAlchemy 2.0** with `Mapped` and `mapped_column` syntax for robust, type-safe database interactions.
- **Security Layer:** Implements JWT-based stateless authentication and PBKDF2-driven password hashing with Role-Based Access Control (RBAC).
- **High-Precision Cache Layer:** Leverages **Redis** for sub-second transaction velocity tracking and idempotency replay.

## Professional Tech Stack
- **Framework:** FastAPI (High-performance, async-native)
- **ORM:** SQLAlchemy 2.0 (Industry-standard data modeling)
- **Validation:** Pydantic v2 (Strict typing and performance)
- **Migrations:** Alembic (Versioned schema evolution)
- **Database:** PostgreSQL (Production-ready relational storage)
- **Cache:** Redis (Transaction velocity & Idempotency)
- **Testing:** Pytest & HTTPX (Comprehensive integration and unit testing)
- **Scheduling:** APScheduler (Automated daily billing jobs)
- **Logging:** Structured JSON logging (Production-grade observability)

## Key Features
- **Sophisticated Underwriting:** Automated risk scoring engine for real-time application decisions.
- **Enterprise-Grade Security:** Comprehensive JWT-based auth flow and encrypted sensitive data handling.
- **Unified OTP Dispatcher:** Centralized service for registration, password resets, and transaction verification.
- **Lifecycle Management:** Dedicated modules for card issuance, activation, blocking, and account adjustments.
- **Billing & Statements:** ADB-based interest computation, grace period heuristics, and automated statement generation.
- **Payment Processing (RBI Waterfall):** Strict Fees → Interest → Cash Advance → Purchase allocation per RBI mandate.
- **Advanced Transaction Core:** 
    - **Redis Velocity:** 4-tier sliding window counters (1m, 10m, 1h, 24h).
    - **Geographic Risk:** Automatic flagging for country-hops < 2h.
    - **Strict Idempotency:** Exactly-once semantics using UUID v4 keys.
- **State-Machine Disputes:** Hardened dispute lifecycle with deadline enforcement and mandatory resolution codes.
- **Scheduled Jobs:** APScheduler-powered daily statement generation (00:01 UTC) and late fee application (00:05 UTC).

## API Architecture (Consolidated)
The system has been refactored into a consolidated, command-driven API:

| Endpoint | Logic Consolidated From | Description |
|----------|-------------------------|-------------|
| `POST /cards/{id}/transactions` | `clearing.py`, `holds.py` | Transaction initiation (Auth + Hold) |
| `PATCH /transactions/{id}` | `void`, `reverse`, `capture` | State transition dispatcher |
| `POST /settlements` | `clearing.py` absorption | 8-step settlement & clearing pipeline |
| `PATCH /disputes/{id}` | `evidence`, `escalate` | Dispute state machine |
| `PATCH /fees` | `interest.py`, `waive.py` | Fee application & waiver dispatcher |

## Getting Started

### 1. Prerequisite Setup
Ensure you have Python 3.10+, PostgreSQL, and **Redis** running.

```bash
# Clone the repository
git clone https://github.com/swaggyV08/Credit-Card-System.git
cd Credit-Card-System

# Initialize virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
```

### 2. Dependency Installation
```bash
pip install -r requirements.txt
```

### 3. Database & Cache Configuration
1. Create a database named `credit_card_db` in PostgreSQL.
2. Update the `DATABASE_URL` and `REDIS_URL` in `.env`.

### 4. Schema Evolution
```bash
alembic upgrade head
```

### 5. Application Launch
```bash
uvicorn app.main:app --reload --port 8082
```
Interactive Docs: [http://localhost:8082/docs](http://localhost:8082/docs)

### 6. Running Tests
```bash
pytest --cov=app --cov-report=term-missing tests/
```

---
**Vishnu P**
*Backend Developer | Python Developer*
