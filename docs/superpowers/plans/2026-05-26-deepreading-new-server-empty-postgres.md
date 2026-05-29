# Deep Reading New Server Empty PostgreSQL Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a fresh Deep Reading Agent instance on `8.162.14.154:18080` with an empty PostgreSQL database, while leaving the existing exam system on port `80` untouched.

**Architecture:** The existing exam system remains `Nginx :80 -> Gunicorn 127.0.0.1:5000`. Deep Reading gets its own directory, virtualenv, PostgreSQL database/user, systemd service, internal FastAPI port `18000`, and external Nginx port `18080`. No old SQLite data is migrated; the old Deep Reading server remains a backup/archive.

**Tech Stack:** FastAPI, React/Vite, SQLAlchemy async, Alembic, PostgreSQL, Nginx, systemd, Python 3.11.

---

## Confirmed Server State

Checked on `2026-05-26`:

```text
Server: 8.162.14.154
OS: Alibaba Cloud Linux 3
CPU/RAM: 2 cores / 1.8 GiB RAM / 8 GiB swap
Disk: 40G root volume, about 19G available
Existing app: exam-system-online.service
Existing app internal port: 127.0.0.1:5000
Existing public port: Nginx :80
Existing Nginx config: /etc/nginx/conf.d/exam-system-online.conf
PostgreSQL: not installed/running at inspection time
Redis: not installed/running at inspection time
Python 3.11: /usr/bin/python3.11 exists
Candidate ports 18080 and 18000: not occupied at inspection time
```

Port ownership after deployment:

```text
80      existing exam system, do not change
5000    existing exam system Gunicorn, do not change
18080   Deep Reading public Nginx port
18000   Deep Reading internal FastAPI port, localhost only
5432    PostgreSQL, localhost only
```

Because the server has limited memory, start with one API worker and conservative task concurrency. Redis/Celery can be added after the PostgreSQL deployment is stable.

---

## Files And Responsibilities

### Local Repository Files

- Modify: `requirements.txt`
  - Add PostgreSQL runtime dependencies.
- Modify: `backend/db/session.py`
  - Ensure `postgresql+asyncpg` works for the app and maps to `postgresql+psycopg2` for Alembic.
- Verify: `backend/migrations/env.py`
  - Confirm Alembic reads `SYNC_DATABASE_URL`.
- Verify: `backend/migrations/versions/*.py`
  - Confirm all migrations can run against PostgreSQL from an empty database.
- Verify: `backend/main.py`
  - Confirm health endpoint and static frontend serving behavior.
- Verify or create: admin/invite seed command
  - Identify the existing script/endpoint for first admin or invite code creation.

### Server Files

- Create: `/root/deep-reading-agent`
  - Fresh checkout of this repository.
- Create: `/root/deep-reading-agent/venv`
  - Dedicated Python virtualenv.
- Create: `/root/deep-reading-agent/.env.production`
  - Deep Reading production environment variables.
- Create: `/var/log/deepreading/`
  - Dedicated logs for Deep Reading.
- Create: `/etc/nginx/conf.d/deepreading-18080.conf`
  - Nginx server block for public port `18080`.
- Create: `/etc/systemd/system/deepreading-api.service`
  - systemd service for FastAPI.

### PostgreSQL Objects

- Create database user: `deepreading`
- Create database: `deepreading`
- Optional dry-run database: `deepreading_dryrun`

---

## Task 1: Local PostgreSQL Compatibility Check

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/db/session.py`
- Verify: `backend/migrations/env.py`

- [ ] **Step 1: Inspect current database session code**

Run:

```powershell
Get-Content backend/db/session.py
Get-Content backend/migrations/env.py
```

Expected:

```text
backend/db/session.py defines DATABASE_URL and SYNC_DATABASE_URL
backend/migrations/env.py imports SYNC_DATABASE_URL
```

- [ ] **Step 2: Add PostgreSQL dependencies**

Modify `requirements.txt` to include:

```text
asyncpg>=0.29.0
psycopg2-binary>=2.9.9
```

Keep `aiosqlite` because local development and rollback still need SQLite support.

- [ ] **Step 3: Ensure database URL mapping is correct**

In `backend/db/session.py`, ensure this mapping exists:

```python
if DATABASE_URL.startswith("postgresql+asyncpg"):
    SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
elif DATABASE_URL.startswith("sqlite+aiosqlite"):
    SYNC_DATABASE_URL = DATABASE_URL.replace("sqlite+aiosqlite", "sqlite", 1)
elif DATABASE_URL.startswith("sqlite"):
    SYNC_DATABASE_URL = DATABASE_URL
else:
    SYNC_DATABASE_URL = DATABASE_URL
```

Also ensure PostgreSQL engine kwargs do not pass SQLite-only settings:

```python
engine_kwargs = {"echo": False, "future": True}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    engine_kwargs.update(
        pool_size=5,
        max_overflow=5,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

engine = create_async_engine(DATABASE_URL, **engine_kwargs)
```

Use a small pool because this server has only 1.8 GiB RAM.

- [ ] **Step 4: Run local syntax checks**

Run:

```powershell
python -m py_compile backend/db/session.py backend/migrations/env.py
```

Expected:

```text
No output and exit code 0
```

- [ ] **Step 5: Run current backend queue test**

Run:

```powershell
python -m unittest backend.tests.test_queue_manager
```

Expected:

```text
OK
```

- [ ] **Step 6: Commit local compatibility changes**

Only after tests pass:

```powershell
git add requirements.txt backend/db/session.py
git commit -m "chore: support postgres database url"
```

---

## Task 2: Server Base Package Preparation

**Files:**
- Server only.

- [ ] **Step 1: Confirm existing exam system is healthy**

Run on the server:

```bash
systemctl status exam-system-online --no-pager
curl -I http://127.0.0.1:5000/
curl -I http://127.0.0.1/
```

Expected:

```text
exam-system-online.service is active
127.0.0.1:5000 responds
127.0.0.1 through Nginx responds
```

- [ ] **Step 2: Install system packages**

Run:

```bash
dnf install -y git nginx postgresql-server postgresql-contrib postgresql-devel gcc python3.11 python3.11-devel nodejs npm
```

Expected:

```text
Packages install successfully
```

- [ ] **Step 3: Initialize PostgreSQL if not initialized**

Run:

```bash
test -f /var/lib/pgsql/data/PG_VERSION || postgresql-setup --initdb
systemctl enable --now postgresql
systemctl status postgresql --no-pager
```

Expected:

```text
postgresql.service is active
```

- [ ] **Step 4: Confirm PostgreSQL is local-only**

Run:

```bash
ss -tulpen | grep ':5432'
```

Expected:

```text
PostgreSQL listens on 127.0.0.1:5432 or local socket only
It must not listen on 0.0.0.0:5432
```

---

## Task 3: Create Empty PostgreSQL Database

**Files:**
- Server only.

- [ ] **Step 1: Generate a database password**

Run:

```bash
openssl rand -base64 32
```

Save the output temporarily as `DEEPREADING_DB_PASSWORD`. Do not commit it to git.

- [ ] **Step 2: Create database user and database**

Run as root:

```bash
sudo -u postgres psql
```

Inside `psql`, run:

```sql
CREATE USER deepreading WITH PASSWORD 'replace_with_generated_password';
CREATE DATABASE deepreading OWNER deepreading;
GRANT ALL PRIVILEGES ON DATABASE deepreading TO deepreading;
\q
```

- [ ] **Step 3: Verify database login**

Run:

```bash
psql "postgresql://deepreading:replace_with_generated_password@127.0.0.1:5432/deepreading" -c "SELECT current_database(), current_user;"
```

Expected:

```text
current_database = deepreading
current_user = deepreading
```

---

## Task 4: Deploy Code Into Isolated Directory

**Files:**
- Create: `/root/deep-reading-agent`
- Create: `/root/deep-reading-agent/.env.production`
- Create: `/var/log/deepreading/`

- [ ] **Step 1: Clone or update repository**

If the directory does not exist:

```bash
cd /root
git clone https://github.com/lxjthu/deep-reading-agent.git deep-reading-agent
cd /root/deep-reading-agent
git switch online
```

If the directory already exists:

```bash
cd /root/deep-reading-agent
git fetch origin online
git switch online
git pull --ff-only origin online
```

- [ ] **Step 2: Create virtualenv**

Run:

```bash
cd /root/deep-reading-agent
/usr/bin/python3.11 -m venv venv
./venv/bin/python -m pip install --upgrade pip wheel setuptools
```

- [ ] **Step 3: Install Python dependencies**

Run:

```bash
cd /root/deep-reading-agent
./venv/bin/pip install -r requirements.txt
```

Expected:

```text
FastAPI, SQLAlchemy, Alembic, asyncpg, and psycopg2-binary install successfully
```

- [ ] **Step 4: Create production environment file**

Create `/root/deep-reading-agent/.env.production`:

```bash
cat > /root/deep-reading-agent/.env.production <<'EOF'
DATABASE_URL=postgresql+asyncpg://deepreading:replace_with_generated_password@127.0.0.1:5432/deepreading
ENVIRONMENT=production
PYTHONUNBUFFERED=1
EOF
chmod 600 /root/deep-reading-agent/.env.production
```

Do not include a shared DeepSeek API key. Web mode users provide their own key from the frontend.

- [ ] **Step 5: Create log directory**

Run:

```bash
mkdir -p /var/log/deepreading
```

---

## Task 5: Build Empty PostgreSQL Schema With Alembic

**Files:**
- Uses: `backend/migrations/`
- Uses: `/root/deep-reading-agent/.env.production`

- [ ] **Step 1: Run Alembic upgrade against PostgreSQL**

Run:

```bash
cd /root/deep-reading-agent/backend
set -a
source /root/deep-reading-agent/.env.production
set +a
../venv/bin/python -m alembic upgrade head
```

Expected:

```text
Alembic applies all migrations to PostgreSQL without SQLite-specific errors
```

- [ ] **Step 2: Verify Alembic head**

Run:

```bash
cd /root/deep-reading-agent/backend
set -a
source /root/deep-reading-agent/.env.production
set +a
../venv/bin/python -m alembic current
../venv/bin/python -m alembic heads
```

Expected:

```text
current and heads show the same latest migration
```

- [ ] **Step 3: Verify core tables exist**

Run:

```bash
psql "postgresql://deepreading:replace_with_generated_password@127.0.0.1:5432/deepreading" -c "\dt"
psql "postgresql://deepreading:replace_with_generated_password@127.0.0.1:5432/deepreading" -c "SELECT version_num FROM alembic_version;"
```

Expected tables include:

```text
users
files
bib_entries
jobs
reading_items
artifacts
prompt_templates
dimension_sets
dimension_items
```

---

## Task 6: Initialize Admin Or Invite Flow

**Files:**
- Inspect: `backend/auth/`
- Inspect: `backend/routers/auth.py`
- Inspect: repository scripts for admin/invite seed.

- [ ] **Step 1: Locate existing seed mechanism**

Run locally or on the server:

```bash
cd /root/deep-reading-agent
grep -R "seed" -n backend scripts . | head -80
grep -R "invite" -n backend scripts . | head -80
grep -R "admin" -n backend scripts . | head -120
```

Expected:

```text
Identify the existing supported way to create the first admin user or invite code
```

- [ ] **Step 2: Use the existing supported seed path**

If the app already has an admin seed script, run it with the production env loaded:

```bash
cd /root/deep-reading-agent
set -a
source /root/deep-reading-agent/.env.production
set +a
./venv/bin/python path/to/existing_seed_script.py
```

If the app supports first-user registration as admin, skip seeding and create the first admin through the web UI after deployment.

If the app requires invite codes, generate one using the existing script or endpoint and store it outside git.

- [ ] **Step 3: Verify admin or invite data**

Run:

```bash
psql "postgresql://deepreading:replace_with_generated_password@127.0.0.1:5432/deepreading" -c "SELECT id, username, role FROM users LIMIT 5;"
psql "postgresql://deepreading:replace_with_generated_password@127.0.0.1:5432/deepreading" -c "SELECT * FROM invite_codes LIMIT 5;"
```

Expected:

```text
Either an admin user exists, or a valid invite code exists
```

---

## Task 7: Build Frontend For Production

**Files:**
- Uses: `frontend/`
- Verify: `backend/main.py` static serving.

- [ ] **Step 1: Install frontend dependencies**

Run:

```bash
cd /root/deep-reading-agent/frontend
npm install
```

Expected:

```text
node_modules installs successfully
```

- [ ] **Step 2: Build frontend**

Run:

```bash
cd /root/deep-reading-agent/frontend
npm run build
```

Expected:

```text
frontend/dist is created
```

- [ ] **Step 3: Confirm backend can serve built frontend**

Inspect `backend/main.py`:

```bash
grep -n "StaticFiles\|frontend\|dist\|FileResponse" /root/deep-reading-agent/backend/main.py
```

Expected:

```text
FastAPI serves frontend/dist or equivalent production static assets
```

If the current online deployment still depends on a separate Vite dev server, stop and update the deployment design before proceeding. The preferred production shape for this server is one internal FastAPI port, not an extra public Vite port.

---

## Task 8: Create Deep Reading API systemd Service

**Files:**
- Create: `/etc/systemd/system/deepreading-api.service`

- [ ] **Step 1: Create service file**

Run:

```bash
cat > /etc/systemd/system/deepreading-api.service <<'EOF'
[Unit]
Description=Deep Reading Agent API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
User=root
WorkingDirectory=/root/deep-reading-agent/backend
EnvironmentFile=/root/deep-reading-agent/.env.production
ExecStart=/root/deep-reading-agent/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 18000 --workers 1 --timeout-keep-alive 30
Restart=always
RestartSec=5
StandardOutput=append:/var/log/deepreading/api.log
StandardError=append:/var/log/deepreading/api-error.log

[Install]
WantedBy=multi-user.target
EOF
```

- [ ] **Step 2: Start service**

Run:

```bash
systemctl daemon-reload
systemctl enable --now deepreading-api
systemctl status deepreading-api --no-pager
```

Expected:

```text
deepreading-api.service is active
```

- [ ] **Step 3: Verify internal API port**

Run:

```bash
ss -tulpen | grep ':18000'
curl -i http://127.0.0.1:18000/health
curl -i http://127.0.0.1:18000/
```

Expected:

```text
18000 listens on 127.0.0.1
Health endpoint returns success if implemented
Root endpoint returns API info or frontend HTML
```

---

## Task 9: Add Nginx Port 18080 Without Touching Exam System

**Files:**
- Create: `/etc/nginx/conf.d/deepreading-18080.conf`
- Do not modify: `/etc/nginx/conf.d/exam-system-online.conf`

- [ ] **Step 1: Create Nginx config**

Run:

```bash
cat > /etc/nginx/conf.d/deepreading-18080.conf <<'EOF'
server {
    listen 18080;
    server_name _;

    client_max_body_size 200m;
    server_tokens off;

    location / {
        proxy_pass http://127.0.0.1:18000;
        proxy_http_version 1.1;
        proxy_set_header Host $host:$server_port;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:18000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host:$server_port;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
EOF
```

- [ ] **Step 2: Validate and reload Nginx**

Run:

```bash
nginx -t
systemctl reload nginx
systemctl status nginx --no-pager
```

Expected:

```text
nginx -t succeeds
nginx remains active
```

- [ ] **Step 3: Verify port 18080 locally**

Run:

```bash
ss -tulpen | grep ':18080'
curl -i http://127.0.0.1:18080/
```

Expected:

```text
Nginx listens on 0.0.0.0:18080 or [::]:18080
The request reaches Deep Reading
```

- [ ] **Step 4: Verify exam system still works**

Run:

```bash
curl -I http://127.0.0.1/
curl -I http://127.0.0.1:5000/
systemctl status exam-system-online --no-pager
```

Expected:

```text
Exam system still responds
exam-system-online.service remains active
```

---

## Task 10: Public Network Verification

**Files:**
- None.

- [ ] **Step 1: Verify from local machine**

Run from Windows PowerShell:

```powershell
Test-NetConnection 8.162.14.154 -Port 18080
```

Expected:

```text
TcpTestSucceeded: True
```

- [ ] **Step 2: Open new Deep Reading URL**

Open:

```text
http://8.162.14.154:18080/
```

Expected:

```text
Deep Reading login/register page loads
```

- [ ] **Step 3: Verify existing exam system URL**

Open:

```text
http://8.162.14.154/
```

Expected:

```text
Existing exam system still loads
```

---

## Task 11: Functional Smoke Test

**Files:**
- None unless a bug is found.

- [ ] **Step 1: Register or create first user**

Use the selected admin/invite flow from Task 6.

Expected:

```text
The first user can log in
Role is admin or expected initial role
```

- [ ] **Step 2: Set DeepSeek API key**

In the frontend, set a user DeepSeek API key.

Expected:

```text
Key is accepted by the frontend
No server-side .env fallback is required
```

- [ ] **Step 3: Upload a small PDF or Markdown file**

Expected:

```text
Upload succeeds
File appears in the app/library flow
```

- [ ] **Step 4: Run one small reading task**

Use a short Markdown file or small PDF to avoid expensive first-run tests.

Expected:

```text
Job is created
Progress updates
Final artifact is visible
PostgreSQL jobs/artifacts rows are created
```

- [ ] **Step 5: Verify PostgreSQL rows**

Run:

```bash
psql "postgresql://deepreading:replace_with_generated_password@127.0.0.1:5432/deepreading" -c "SELECT COUNT(*) FROM users;"
psql "postgresql://deepreading:replace_with_generated_password@127.0.0.1:5432/deepreading" -c "SELECT COUNT(*) FROM files;"
psql "postgresql://deepreading:replace_with_generated_password@127.0.0.1:5432/deepreading" -c "SELECT COUNT(*) FROM jobs;"
psql "postgresql://deepreading:replace_with_generated_password@127.0.0.1:5432/deepreading" -c "SELECT COUNT(*) FROM artifacts;"
```

Expected:

```text
Counts reflect the smoke-test actions
```

- [ ] **Step 6: Check logs**

Run:

```bash
tail -100 /var/log/deepreading/api.log
tail -100 /var/log/deepreading/api-error.log
tail -100 /var/log/nginx/error.log
```

Expected:

```text
No repeated 500 errors
No connection refused errors to 127.0.0.1:18000
No PostgreSQL authentication errors
```

---

## Task 12: Conservative Concurrency Guardrails

**Files:**
- Inspect: `backend/services/queue_manager.py`
- Inspect: reading/translation/reference routers.

- [ ] **Step 1: Inspect current queue limits**

Run:

```bash
cd /root/deep-reading-agent
grep -R "MAX_CONCURRENT\|concurrent\|queue" -n backend/services backend/routers | head -120
```

Expected:

```text
Identify current global and per-user task limits
```

- [ ] **Step 2: Set initial production limits conservatively**

For this 2-core/1.8GiB server, start with:

```text
Global heavy task concurrency: 2
Per-user heavy task concurrency: 1 or 2
Translation chunk worker concurrency: 2 or 3
API worker count: 1
```

If these are controlled by constants, update code in a separate commit. If they are controlled by env vars, add them to `.env.production`.

- [ ] **Step 3: Re-run smoke test after limit changes**

Run:

```bash
systemctl restart deepreading-api
curl -i http://127.0.0.1:18080/
```

Expected:

```text
Deep Reading still starts and responds
```

---

## Task 13: Rollback Procedure

**Files:**
- Server only.

- [ ] **Step 1: Stop Deep Reading only**

Run:

```bash
systemctl stop deepreading-api
```

Expected:

```text
Deep Reading internal port 18000 stops
Exam system remains active
```

- [ ] **Step 2: Remove only Deep Reading Nginx config**

Run:

```bash
rm -f /etc/nginx/conf.d/deepreading-18080.conf
nginx -t
systemctl reload nginx
```

Expected:

```text
Nginx reloads successfully
Port 18080 no longer serves Deep Reading
Port 80 still serves exam system
```

- [ ] **Step 3: Verify exam system after rollback**

Run:

```bash
systemctl status exam-system-online --no-pager
curl -I http://127.0.0.1/
curl -I http://8.162.14.154/
```

Expected:

```text
Exam system is unaffected
```

PostgreSQL database can remain in place for later debugging. Do not drop it during emergency rollback unless explicitly requested.

---

## Task 14: Post-Deployment Notes

**Files:**
- Modify after successful user verification only: `docs/DEPLOYMENT_ARCHITECTURE.md`
- Modify after successful user verification only: `docs/DATABASE_DEPLOY_AND_MIGRATION_GUIDE.md`
- Modify after successful user verification only: `docs/README.md`

- [ ] **Step 1: Wait for user verification**

Do not write completion-style docs before the user confirms the new server works.

- [ ] **Step 2: Update deployment docs after verification**

After successful verification, document:

```text
New public URL: http://8.162.14.154:18080/
Deployment mode: PostgreSQL empty instance
Old Deep Reading server: retained as backup, no migration
Existing exam system: unchanged on http://8.162.14.154/
```

- [ ] **Step 3: Update docs navigation**

Add this deployment note to `docs/README.md` after the deployment is verified.

---

## Self-Review

- Spec coverage: Covers new-server empty database deployment, port isolation, PostgreSQL setup, Nginx `18080`, systemd service, smoke testing, and rollback.
- Placeholder scan: No `TBD` or `TODO`; passwords and repo URL are intentionally marked as runtime secrets/known repository values.
- Scope check: Excludes old SQLite migration by design. Excludes Redis/Celery multi-worker migration from this first deployment because the server is resource-constrained and the user requested a fresh start.
- Risk check: The existing exam system files and service are not modified. Only a new Nginx config is added, and it can be removed independently.
