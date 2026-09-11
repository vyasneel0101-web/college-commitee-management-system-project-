# 09 — Local PostgreSQL Setup (no Docker)

> **Not needed today.** The sprint runs on SQLite. This is debt item 1 in `00_START_HERE.md` §5 — do it after the demo, before the system holds any real record. The switch is one `DATABASE_URL` change plus a fresh `migrate`, because the models and constraints are already written for Postgres.

Target version: **PostgreSQL 18.x** (18.6 is the current stable release as of September 2026). Do not install PostgreSQL 19 — it is still in beta.

Find your operating system below and follow only that section. Then do §4, which everyone needs.

---

## 1. Windows

### 1.1 Install

1. Go to `https://www.postgresql.org/download/windows/` and open the EDB installer download page.
2. Download the **PostgreSQL 18.x** Windows x86-64 installer.
3. Run it. Accept the defaults, with these specifics:
   - **Components:** keep PostgreSQL Server, pgAdmin 4, and Command Line Tools. You can uncheck Stack Builder.
   - **Data directory:** default is fine.
   - **Superuser password:** set one and **write it down**. This is the `postgres` account password. You will need it in a moment and rarely after that.
   - **Port:** `5432`. If the installer says the port is in use, you already have PostgreSQL installed — see §5.1.
   - **Locale:** default.
4. Finish. The server installs as a Windows service and starts automatically, so it will be running after every reboot without you doing anything.

### 1.2 Put `psql` on your PATH

The installer does not do this, and without it every command below fails with "psql is not recognized".

1. Press `Win`, type `environment variables`, open **Edit the system environment variables**.
2. Click **Environment Variables**.
3. Under **System variables**, select `Path`, click **Edit**, then **New**.
4. Add: `C:\Program Files\PostgreSQL\18\bin`
5. OK out of all three dialogs.
6. **Close and reopen your terminal.** PATH changes do not affect already-open windows.

Verify:

```powershell
psql --version
```

You should see `psql (PostgreSQL) 18.x`.

### 1.3 Create the database and user

```powershell
psql -U postgres
```

Enter the superuser password you set. At the `postgres=#` prompt:

```sql
CREATE ROLE cams_user WITH LOGIN PASSWORD 'ChangeMe_Local_2026' CREATEDB;
CREATE DATABASE cams OWNER cams_user;
\q
```

Then go to §4.

---

## 2. macOS

### 2.1 Install

Two good options. **Postgres.app** is simplest.

**Option A — Postgres.app**

1. Download from `https://postgresapp.com/` and drag it to Applications.
2. Open it and click **Initialize**. It starts a PostgreSQL 18 server on port 5432.
3. Add the CLI tools to your PATH:

```bash
sudo mkdir -p /etc/paths.d && echo /Applications/Postgres.app/Contents/Versions/latest/bin | sudo tee /etc/paths.d/postgresapp
```

Close and reopen your terminal.

**Option B — Homebrew**

```bash
brew install postgresql@18
brew services start postgresql@18
echo 'export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Verify either option:

```bash
psql --version
```

### 2.2 Create the database and user

Both installs make your macOS username a superuser, so no password prompt:

```bash
psql postgres
```

```sql
CREATE ROLE cams_user WITH LOGIN PASSWORD 'ChangeMe_Local_2026' CREATEDB;
CREATE DATABASE cams OWNER cams_user;
\q
```

Then go to §4.

---

## 3. Linux (Ubuntu / Debian)

### 3.1 Install

Ubuntu's default repositories usually carry an older major version, so use the PostgreSQL project's own repository:

```bash
sudo apt install -y curl ca-certificates
sudo install -d /usr/share/postgresql-common/pgdg
sudo curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
  --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
sudo sh -c 'echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
  https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list'
sudo apt update
sudo apt install -y postgresql-18
```

Confirm it is running:

```bash
sudo systemctl status postgresql
psql --version
```

### 3.2 Create the database and user

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE cams_user WITH LOGIN PASSWORD 'ChangeMe_Local_2026' CREATEDB;
CREATE DATABASE cams OWNER cams_user;
\q
```

Then go to §4.

---

## 4. Everyone: verify and configure

### 4.1 Test the connection as your application user

```bash
psql -h localhost -U cams_user -d cams -c "SELECT version();"
```

Enter `ChangeMe_Local_2026`. You should see the PostgreSQL 18 version string. **If this command fails, stop and fix it now** — every later phase depends on it, and debugging it later mixed in with Django errors is much harder.

The `-h localhost` is not optional on Linux. See §5.3.

### 4.2 Put the connection string in `.env`

In the repo root, copy `.env.example` to `.env` and set:

```
DATABASE_URL=postgres://cams_user:ChangeMe_Local_2026@localhost:5432/cams
```

`.env` is gitignored. `.env.example` is committed and must never contain a real password.

### 4.3 Why `CREATEDB` on the role

`pytest-django` creates and drops a separate database (`test_cams`) on every run. Without `CREATEDB` the entire test suite fails at collection with a permission error, which looks like a broken test setup rather than a database permission problem. If you skipped it:

```sql
ALTER ROLE cams_user CREATEDB;
```

### 4.4 A note on the password

`ChangeMe_Local_2026` is fine for a local development database that only listens on `localhost`. Use a different, strong password for the production database in Phase 9, and never commit either.

---

## 5. Troubleshooting

### 5.1 "Port 5432 is already in use" during install

An older PostgreSQL is already installed. Either uninstall it (if you don't need it) or install the new one on port `5433` and change `DATABASE_URL` to match. Do not run two servers on the same port.

To see what's listening:

```powershell
netstat -ano | findstr :5432          # Windows
```

```bash
sudo lsof -i :5432                    # macOS / Linux
```

### 5.2 `psql: command not found` / "not recognized"

PATH is not set, or your terminal predates the change. Reopen the terminal first. On Windows, re-check §1.2 and confirm the version number in the path matches your installed version (`18`, not `17`).

### 5.3 `FATAL: Peer authentication failed for user "cams_user"` (Linux)

You connected over a Unix socket, where PostgreSQL tries to match your OS username to the database username. Add `-h localhost` to force a TCP connection, which uses password authentication. Django does this automatically when `DATABASE_URL` contains a host, so this affects manual `psql` commands only.

### 5.4 `FATAL: database "cams" does not exist`

The `CREATE DATABASE` step didn't run, or ran in the wrong session. Reconnect as the superuser and list databases with `\l`.

### 5.5 `password authentication failed for user "cams_user"`

Most often a typo between the `CREATE ROLE` password and `DATABASE_URL`. Reset it:

```sql
ALTER ROLE cams_user WITH PASSWORD 'ChangeMe_Local_2026';
```

Also check the password contains no `@`, `:`, `/`, or `#` — those characters must be percent-encoded inside a `DATABASE_URL` and are a common source of confusing failures. Sticking to letters, digits, and underscores avoids the problem.

### 5.6 Server not running after a reboot

Windows and Linux install it as an auto-starting service, so this is rare. If it happens:

```powershell
Get-Service postgresql*                          # Windows: check
Start-Service postgresql-x64-18                  # Windows: start
```

```bash
brew services start postgresql@18                # macOS Homebrew
sudo systemctl start postgresql                  # Linux
```

Postgres.app must be open for the server to run; set it to launch at login in its preferences.

### 5.7 Django says `ModuleNotFoundError: No module named 'psycopg2'`

We use psycopg 3, not psycopg2. Install `psycopg[binary]` and make sure the `DATABASE_URL` scheme is `postgres://`. The `[binary]` extra ships precompiled wheels, which avoids needing a C compiler on Windows.

---

## 6. Useful commands

```bash
psql -h localhost -U cams_user -d cams     # connect to the project database
```

Inside `psql`:

| Command | Does |
|---|---|
| `\l` | list databases |
| `\dt` | list tables in the current database |
| `\d assignments_assignment` | describe a table, including constraints |
| `\du` | list roles |
| `\x` | toggle expanded output (much more readable for wide rows) |
| `\q` | quit |

`\d` on a table is worth knowing — it prints the actual constraints PostgreSQL is enforcing. When a Phase 1 constraint test behaves oddly, that output tells you whether the constraint really exists in the database or only in your models file.

### Backups

Even locally, take one before anything destructive:

```bash
pg_dump -h localhost -U cams_user -d cams -F c -f cams_backup.dump
pg_restore -h localhost -U cams_user -d cams --clean cams_backup.dump
```

The same two commands, pointed at the production host, are the backup procedure for Phase 9.
