# Database migrations

Use Alembic for production schema changes. Do not use `Base.metadata.create_all()` in production.

Apply migrations locally after configuring `DATABASE_URL`:

```bash
alembic upgrade head
```

Create a new migration after changing models:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

The first migration is checked in at `migrations/versions/0001_initial_schema.py`.
