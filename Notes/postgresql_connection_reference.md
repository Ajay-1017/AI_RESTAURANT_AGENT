# PostgreSQL Connection & Database Management --- Quick Reference

This guide is for connecting to a **local PostgreSQL server on Linux**
and performing common database administration tasks.

---

## 1. PostgreSQL Connection Basics

The standard `psql` connection format is:

```bash
psql -h HOST -p PORT -U USER -d DATABASE
```

Example:

```bash
psql -h localhost -p 5432 -U postgres -d postgres
```

### Meaning of each option

  Option   Meaning                          Example

---

  `psql`   PostgreSQL command-line client   `psql`
  `-h`     Host/server address              `localhost`
  `-p`     PostgreSQL port                  `5432`
  `-U`     PostgreSQL user/role             `postgres`
  `-d`     Database to connect to           `postgres`

So:

```bash
psql -h localhost -p 5432 -U postgres -d postgres
```

means:

> Connect to the PostgreSQL server running on this computer, on port
> 5432, using the `postgres` user, and open the `postgres` database.

---

# 2. If You Don't Know the `postgres` Password

For a local PostgreSQL installation on Linux, you can use the
operating-system `postgres` user.

First, exit `psql` if you are already inside it:

```sql
\q
```

Then run this from the **Linux terminal**, not inside `psql`:

```bash
sudo -u postgres psql
```

If it works, you should see something similar to:

```text
postgres=#
```

This means you successfully entered PostgreSQL as the `postgres`
database administrator without needing to know its database password.

---

# 3. Verify Which PostgreSQL User You Are Using

Inside `psql`, run:

```sql
SELECT current_user;
```

Expected result:

```text
 current_user
--------------
 postgres
```

You can also check the current database:

```sql
SELECT current_database();
```

---

# 4. List All Databases

Inside `psql`:

```sql
\l
```

or:

```sql
\list
```

This shows the databases available on the PostgreSQL server.

---

# 5. Create a Database

If you are logged in as a PostgreSQL administrator:

```sql
CREATE DATABASE ai_restaurant_db;
```

To create the database and make `ajay` its owner:

```sql
CREATE DATABASE ai_restaurant_db OWNER ajay;
```

### Recommended development setup

For your own development projects, using a dedicated owner/application
role is preferable to using the `postgres` superuser for normal
application work.

Example:

```sql
CREATE DATABASE ai_restaurant_db OWNER ajay;
```

---

# 6. Connect to Your Application Database

After creating the database, you can connect to it as `ajay`:

```bash
psql -h localhost -p 5432 -U ajay -d ai_restaurant_db
```

If PostgreSQL asks for a password, enter the password for the `ajay`
PostgreSQL role.

---

# 7. Check the Current Connection

After connecting, run:

```sql
SELECT current_user;
```

and:

```sql
SELECT current_database();
```

For example:

```text
current_user
-------------
ajay

current_database
-----------------
ai_restaurant_db
```

This confirms that you are using the expected user and database.

---

# 8. List Tables

Once connected to your application database:

```sql
\dt
```

This lists the tables in the current database.

To see all tables, including those in different schemas:

```sql
\dt *.*
```

---

# 9. See Database Details

Inside `psql`:

```sql
\conninfo
```

This shows information about your current connection.

For example, it can show the database, user, host, and port being used.

---

# 10. Switch to Another Database

Inside `psql`:

```sql
\c database_name
```

Example:

```sql
\c ai_restaurant_db
```

You can also specify a different user:

```sql
\c ai_restaurant_db ajay
```

---

# 11. Delete a Database

### Important

You cannot normally delete the database you are currently connected to.

For example, if you want to delete:

```text
ai_restaurant_db
```

first connect to another database, such as `postgres`:

```bash
sudo -u postgres psql
```

Then:

```sql
DROP DATABASE ai_restaurant_db;
```

This permanently removes the database and its data.

**Be very careful with `DROP DATABASE`.**

---

# 12. Check PostgreSQL Roles/Users

Inside `psql`:

```sql
\du
```

This shows PostgreSQL roles and their privileges.

You may see roles such as:

```text
postgres
ajay
user_management_app
```

Remember:

- PostgreSQL **role/user** = account used to authenticate
- PostgreSQL **database** = database you connect to

For example:

```bash
-U ajay
```

means:

> Login using the `ajay` PostgreSQL role.

While:

```bash
-d ai_restaurant_db
```

means:

> Connect to the `ai_restaurant_db` database.

---

# 13. Common Connection Commands

## Connect as `postgres`

If you know the password:

```bash
psql -h localhost -p 5432 -U postgres -d postgres
```

## Connect as local Linux PostgreSQL administrator

If you don't know the `postgres` database password:

```bash
sudo -u postgres psql
```

## Connect to an application database

Example:

```bash
psql -h localhost -p 5432 -U ajay -d ai_restaurant_db
```

---

# 14. Recommended Workflow for a New Project

When starting a new local PostgreSQL project:

### Step 1 --- Enter PostgreSQL administrator

```bash
sudo -u postgres psql
```

### Step 2 --- Verify administrator access

```sql
SELECT current_user;
```

Expected:

```text
postgres
```

### Step 3 --- Create the project database

```sql
CREATE DATABASE ai_restaurant_db OWNER ajay;
```

### Step 4 --- Exit

```sql
\q
```

### Step 5 --- Connect using the project user

```bash
psql -h localhost -p 5432 -U ajay -d ai_restaurant_db
```

### Step 6 --- Verify

```sql
SELECT current_user;
SELECT current_database();
```

### Step 7 --- Check tables

```sql
\dt
```

---

# 15. Important Mental Model

Think of PostgreSQL as:

```text
PostgreSQL Server
│
├── Roles / Users
│   ├── postgres
│   ├── ajay
│   └── user_management_app
│
└── Databases
    ├── postgres
    ├── ai_restaurant_db
    └── other_project_db
```

A connection chooses:

```text
Server  → localhost
Port    → 5432
User    → ajay
Database→ ai_restaurant_db
```

Which is represented by:

```bash
psql -h localhost -p 5432 -U ajay -d ai_restaurant_db
```

---

# 16. Quick Cheat Sheet

```bash
# Enter PostgreSQL as the local postgres administrator
sudo -u postgres psql

# Connect using username/password
psql -h localhost -p 5432 -U USER -d DATABASE

# Exit psql
\q

# Show databases
\l

# Show PostgreSQL roles/users
\du

# Show current connection
\conninfo

# Show current user
SELECT current_user;

# Show current database
SELECT current_database();

# List tables
\dt

# Create database
CREATE DATABASE database_name;

# Create database with a specific owner
CREATE DATABASE database_name OWNER username;

# Connect to another database from inside psql
\c database_name

# Delete database — use carefully
DROP DATABASE database_name;
```

---

## Most Important Commands to Remember

If you remember only these three for local development:

```bash
# 1. Become PostgreSQL administrator
sudo -u postgres psql

# 2. Create a project database
CREATE DATABASE ai_restaurant_db OWNER ajay;

# 3. Connect to your project database
psql -h localhost -p 5432 -U ajay -d ai_restaurant_db
```
