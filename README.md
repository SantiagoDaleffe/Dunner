# Egida Recovery Gateway | Serverless Dunning Engine

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi)
![Architecture](https://img.shields.io/badge/Architecture-Event_Driven-orange)
![Infrastructure](https://img.shields.io/badge/IaC-Terraform-purple?logo=terraform)
![Payments](https://img.shields.io/badge/Payments-Stripe-blue?logo=stripe)

An enterprise-grade, event-driven *Dunning* (payment recovery) engine designed to automate and optimize failed payment retries for B2B SaaS platforms. 

Traditional payment recovery relies on monolithic cron-jobs polling a database, which leads to scaling bottlenecks, database locks, and poor fault tolerance. **Egida** solves this by decoupling the ingestion of payment failures from the execution of retries, using a serverless architecture powered by distributed message queues and dynamic, tenant-specific business rules.

## High-Level Cloud & Tech Stack
* **Core API:** FastAPI, Python 3.11, Pydantic, SQLAlchemy (Async)
* **Message Broker & Scheduling:** Upstash QStash (Serverless Kafka/Redis wrapper)
* **Database:** PostgreSQL (Supabase) for Relational State & Tenant Configs
* **Infrastructure as Code (IaC):** Terraform (Railway, Supabase, Upstash providers)
* **Payments & Webhooks:** Stripe API
* **CI/CD & Testing:** GitHub Actions, Pytest, SQLite (in-memory for tests), Docker

---

## 1. The Business Problem & Architectural Solution

In subscription-based businesses, involuntary churn (failed payments due to expired cards, insufficient funds, or network errors) directly impacts MRR. 

### The Flaws of Traditional Systems
* **The Cron-Job Bottleneck:** Querying a database every hour for "payments to retry" creates heavy read-locks. If a batch process fails halfway, tracking which payments were retried becomes a nightmare.
* **Hardcoded Logic:** Applying the same retry logic (e.g., "retry every 3 days") to all failures ignores the root cause. A "stolen card" should never be retried, while "insufficient funds" should wait for a payday.
* **Tight Coupling:** If the payment gateway (Stripe) goes down during a cron execution, events are lost or require manual intervention.

### The Egida Event-Driven Approach
Egida treats every failed payment as an isolated, asynchronous event flowing through a state machine:
1. **Webhook Ingestion (`/webhook/stripe`):** Catches real-time failures directly from the payment processor. Validates the cryptographic signature and immediately returns a `202 Accepted` to prevent gateway timeouts.
2. **Decoupled Processing (`/webhook/process`):** The payload is pushed to QStash. A worker consumes the event, evaluates the specific tenant's business rules, and decides the exact timestamp for the next retry.
3. **Serverless Scheduling:** Instead of a cron-job, Egida leverages QStash's `Not-Before` headers to freeze the event in the cloud for days or weeks.
4. **Execution (`/webhook/execute-retry`):** At the exact scheduled second, the engine awakens, executes the charge against Stripe, updates the database state, and either closes the loop or schedules the next attempt.

## 2. The Dunning Engine (Business Rules)

The core logic resides in `core/engine.py` and evaluates events sequentially. It utilizes an extensible Rule Protocol (`DunningRule`) to allow complex financial logic without altering the base engine.

* **`HardDeclineRule`:** Instantly aborts the recovery process if the bank returns fatal error codes (e.g., `card_stolen`, `fraud_suspected`). This prevents merchant account penalties from payment processors.
* **`ExponentialBackoffRule`:** Calculates the optimal next retry date using `base_hours * 2^(attempts)`. It includes edge-case financial logic, such as artificially shifting Sunday retries to Monday to align with banking clearance days.
* **`HighValueAlertRule`:** Intercepts enterprise-tier payment failures (e.g., >$1,000) to trigger alerts for manual intervention by a billing team.
* **`MaxAttemptsRule`:** Enforces a hard cap on retries to prevent infinite loops and ghost API calls.

## 3. Security, Multi-Tenancy & Data Integrity

Handling financial webhooks requires zero-trust security boundaries.

* **Strict Signature Validation:** Every entry point is cryptographically secured. The Stripe adapter verifies `Stripe-Signature` via HMAC-SHA256, and QStash endpoints verify `Upstash-Signature` using rotating asymmetric keys.
* **Idempotency Locks:** To prevent double-charging a customer due to network retries, every event is ingested with an `event_id`. The database performs an ACID-compliant `SELECT 1` check before enqueuing to guarantee exactly-once processing.
* **B2B Multi-Tenancy:** Configurations and rules are stored per `tenant_id`. The engine dynamically loads the correct retry strategy depending on which of the platform's clients owns the failed invoice.
* **Payload Limiting:** An ASGI Middleware (`LimitUploadSize`) drops payloads larger than 1MB at the socket level to prevent memory exhaustion / DoS attacks.

## 4. Infrastructure as Code (IaC) & CI/CD

The platform is designed to be ephemeral and easily reproducible using **Terraform**.

* **Railway Serverless:** The infrastructure provisions a Railway project and dynamically injects all secret keys across environments. The FastAPI service is configured to sleep when idle (`sleepApplication = true`) to optimize cloud costs.
* **Automated CI/CD Pipeline:** Powered by GitHub Actions. On every pull request:
  1. Bootstraps an ephemeral environment.
  2. Runs a `docker compose` health check against the `/health` endpoint to guarantee container stability.
  3. Executes the full `pytest` suite. Database dependencies are mocked using an in-memory SQLite engine (`sqlite+aiosqlite:///:memory:`) to ensure tests are fast and deterministic.

---

## 5. Known Limitations & Roadmap

Transparency is key in enterprise software. The following areas represent the technical debt and future roadmap for Egida:

* **Terraform Provider Constraints:** The community Railway Terraform provider currently struggles with the `sleepApplication` argument on Free/Hobby tiers due to recent API changes by Railway. Manual toggling via the Railway dashboard is temporarily required for zero-cost environments.
* **Gateway Agnosticism:** Currently, the execution phase is tightly coupled to the `stripe` SDK. The roadmap includes an Adapter pattern to support Braintree, Adyen, and MercadoPago simultaneously.
* **Lack of User Communications:** The engine handles the mathematical retries perfectly, but lacks an outgoing communication layer. Future iterations will integrate SendGrid/Resend to trigger localized "Update your payment method" emails on specific attempt milestones.
* **No Frontend Control Panel:** Tenant rules must be upserted via the `/config/rules` API endpoint. A React/Next.js dashboard for billing operations teams is required for full operational maturity.

---

## 6. Local Setup & Deployment

### Prerequisites
* Docker & Docker Compose
* Accounts: Stripe (Test Mode), Upstash (QStash), Supabase
* Terraform `~> 1.5.0`

### Quickstart (Docker)

1. Clone the repository and configure your `.env` file:
   ```bash
   cp infra/.env.example infra/.env
   ```
2. Inject your Supabase DB URL, Stripe Secret, and QStash Tokens.
3. Spin up the cluster:
    ```bash
    cd infra
    docker compose up -d --build
    ```
4. Expose your local port 8000 via ngrok to receive webhooks from Stripe and QStash.

### Cloud Deployment (Terraform)

1. Navigate to the IaC directory:
    ```bash
    cd infra/terraform
    ```
2. Initialize and apply the infrastructure:
    ```bash
    terraform init
    terraform plan
    terraform apply
    ```
3. Copy your newly generated Railway public URL and register it in the Stripe Developer Dashboard to begin listening to `payment_intent.payment_failed` events.
