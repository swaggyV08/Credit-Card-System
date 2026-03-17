# Credit Card Management System

A robust, enterprise-grade backend for managing the complete lifecycle of credit cards, credit accounts, and related backend workflows.

## Table of Contents
1. [System Overview](#system-overview)
2. [Logical Architecture & Flow](#logical-architecture--flow)
3. [Key Modules & Endpoints](#key-modules--endpoints)
    - [Application & Review Workflow](#application--review-workflow)
    - [Credit Account Management](#credit-account-management)
    - [Card Servicing & Lifecycle Operations](#card-servicing--lifecycle-operations)
4. [Deployment & Running Locally](#deployment--running-locally)

---

## System Overview
This repository contains a FastAPI-based backend capable of simulating banking workflows. It tracks and structures entities from physical **Card Products**, mapping them to larger abstracted **Credit Accounts**, all the way up to processing **User Applications** through Maker/Checker style validation.

## Logical Architecture & Flow
The entire process maps a typical customer journey in retail banking:

1. **Credit Product Registration** (Admin Task)
   - Admins define underlying Credit Policies, Interest Frameworks, and GL Accounting Mappings. (`/admin/credit-products/`)

2. **Card Product Definition** (Admin Task)
   - Admins define a physical or virtual variant containing explicit Transaction Controls, Usage Limits, Rewards Config, etc., linked directly to an overarching Credit Product. (`/admin/card-products/`)

3. **Customer Application** 
   - Customers apply for a specific Card Product by submitting their demographic and financial state.
   - This submission triggers KYC validations and Underwriting processes. (`/applications/`)

4. **Underwriting & Review** (Admin Task)
   - Once the application's details are stored, it is automatically scored, but final approval is routed through the Risk & Compliance endpoints for approval. (`/admin/applications/{id}/review`)
   - Approval automatically spins up a **Credit Account** possessing the prescribed credit limits and billing cycle details.

5. **Card Issuance** 
   - A newly established Credit Account warrants issuing a physical/virtual card to the user.
   - Endpoint: `POST /card_product/{credit_account_id}/card`

6. **Card Activation (OTP + PIN Flow)**
   - The user receives their card and activates it via a secure mechanism involving OTPs and custom PIN setup.
   - **Generate OTP**: `POST /auth/otp/generate`
   - **Verify OTP**: `POST /auth/otp/verify`
   - **Activate**: `POST /cards/{card_id}/activate?command=activate` (requires PIN and previous activation_id)

7. **Card Lifecycle Actions** 
   - Users/Admins can manage the active status of the card through the master Dispatcher endpoint `POST /cards/{card_id}?command={action}`.
   - Actions include: `block`, `unblock_otp`, `unblock`, `replace`, `terminate`, `renew`.
   - Modifying a card's state synchronously updates the associated Credit Account statuses and validates internal policies.

---

## Key Modules & Endpoints

### Application & Review Workflow
* Handles both user submissions and risk management administration.

| Route | Method | Description |
| :--- | :--- | :--- |
| `/applications/` | `POST` | User submits demographics to begin the issuance journey. |
| `/admin/applications/{id}/evaluate` | `POST` | Pulls simulated Credit Bureau records & computes fraud probability. |
| `/admin/applications/{id}/review` | `POST` | Approves/Rejects the application. If approved, establishes a `CreditAccount`. |

### Credit Account Management
* Represents the actual underlying line of credit. Modifying limits or freezing is done at this layer.

| Route | Method | Description |
| :--- | :--- | :--- |
| `/admin/credit-accounts/{id}/limits` | `PUT` | Update the `new_credit_limit`, adjusting the total exposure available. |
| `/admin/credit-accounts/{id}/status` | `PUT` | Suspend or close an entire account (`reason_code`, `status`). |
| `/admin/credit-accounts/{id}/freeze` | `POST` | Apply a temporary hold universally across all issued cards linked here. |
| `/admin/credit-accounts/{id}/interest-config` | `PUT` | Change dynamic APR properties (Purchase APR, Cash APR, Penalty APR). |
| `/admin/credit-accounts/{id}/adjustments` | `POST` | Inject manual ledger adjustments (fee waivers, chargebacks). |

### Card Servicing & Lifecycle Operations
* The management of physical/virtual PANs tied to a `CreditAccount`. These actions modify direct card capabilities (International/Domestic/E-commerce toggles).

| Route | Method | Description |
| :--- | :--- | :--- |
| `/card_product/{credit_account_id}/card` | `POST` | **[Issue Card]** Instantiate a new card tied to an account. |
| `/cards/{card_id}/activate` | `POST` | **[Activate]** Requires query parametar `command=activate`, plus OTP ID and PIN. |
| `/cards/{card_id}` | `POST` | **[Lifecycle Dispatcher]** Execute `block`, `unblock`, `terminate`, `renew`, `replace` depending on the `?command=` query param. |
| `/cards/{card_id}/transactions` | `GET` | View a ledger snippet of recent cleared and pending card charges. |

> **Note**: This application heavily enforces case-sensitive validation internally but utilizes automatic `lower()` coercions for most Identity strings (like `merchant_name`, schema IDs, `_code` parameters) via strong Pydantic `field_validators`.

---

## Deployment & Running Locally

1. Install dependencies (e.g., via `pip` or standard Virtual Environment).
2. Configure environment defaults for Database integration (typically via `sqlite` out-of-the-box or standard PostgreSQL config).
3. Use `uvicorn` to mount the FastAPI runtime:

```bash
uvicorn app.main:app --reload
```

Then visit the generated swagger documentation at `http://127.0.0.1:8000/docs` to interact visually with the API.
