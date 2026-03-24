# ZBANQUe Credit Card Management System

## Overview
**ZBANQUe** is a production-grade Credit Card Management System architected for reliability, security, and developer ergonomics. Built with the modern Python ecosystem, it leverages asynchronous patterns and type-safe data modeling to handle the entire credit card lifecycle—from complex underwriting and KYC verification to real-time transaction processing.

## Architecture & Design Patterns
The system is built on a **Layered Architecture** with strict separation of concerns, ensuring high maintainability and testability:

- **API Layer (Controller):** FastAPI routers handling request orchestration, serialization, and OpenAPI documentation.
- **Service Layer:** Houses the core business logic, domain services (e.g., Underwriting Engine, OTP Dispatcher), and transactional workflows.
- **Data Layer (Repository):** Utilizes **SQLAlchemy 2.0** with `Mapped` and `mapped_column` syntax for robust, type-safe database interactions.
- **Security Layer:** Implements JWT-based stateless authentication and PBKDF2-driven password hashing with Role-Based Access Control (RBAC).

## Professional Tech Stack
- **Framework:** FastAPI (High-performance, async-native)
- **ORM:** SQLAlchemy 2.0 (Industry-standard data modeling)
- **Validation:** Pydantic v2 (Strict typing and performance)
- **Migrations:** Alembic (Versioned schema evolution)
- **Database:** PostgreSQL (Production-ready relational storage)
- **Testing:** Pytest & HTTPX (Comprehensive integration and unit testing)

## Key Features
- **Sophisticated Underwriting:** Automated risk scoring engine for real-time application decisions.
- **Enterprise-Grade Security:** Comprehensive JWT-based auth flow and encrypted sensitive data handling.
- **Unified OTP Dispatcher:** Centralized service for registration, password resets, and transaction verification.
- **Lifecycle Management:** Dedicated modules for card issuance, activation, blocking, and account adjustments.
- **Billing & Ledger:** Robust financial tracking with transaction history and account ledgering.

## Getting Started

### 1. Prerequisite Setup
Ensure you have Python 3.10+ and a PostgreSQL instance running.

```bash
# Clone the repository
git clone https://github.com/swaggyV08/Credit-Card-System.git
cd Credit-Card-System

# Initialize virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
```

### 2. Dependency Installation
The project uses a lean `requirements.txt` containing only direct, top-level dependencies.
```bash
pip install -r requirements.txt
```

### 3. Database Configuration
1. Create a database named `credit_card_db` in PostgreSQL.
2. Update the `DATABASE_URL` in `.env` (copy from `.env.example` if provided) or `app/core/config.py`.

### 4. Schema Evolution
Initialize the database schema using Alembic:
```bash
alembic upgrade head
```

### 5. Application Launch
Start the development server with Uvicorn:
```bash
uvicorn app.main:app --reload --port 8082
```
Access the interactive API documentation at: [http://localhost:8082/docs](http://localhost:8082/docs)

---
**Vishnu P**
*Senior Backend Developer | Python Expert*
