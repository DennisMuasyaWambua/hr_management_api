"""
Convert attendance_events into a TimescaleDB hypertable.

Runs only when the connection is PostgreSQL with the timescaledb extension
available (i.e. the 'timescale' DB alias when TIMESCALE_ENABLED). On SQLite or
plain Postgres this is a no-op, so dev environments keep working.

Hypertable requirements: the partition column (`time`) must be part of every
unique constraint, so the surrogate PK becomes (id, time). Adds a 90-day
retention-friendly chunk interval (7 days) and a continuous-aggregate-ready
index. Retention/compression policies are left to ops (documented in
ECOSYSTEM.md) so no data is silently dropped.
"""
from django.db import migrations


def make_hypertable(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != 'postgresql':
        return
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_available_extensions WHERE name='timescaledb'")
        if cur.fetchone() is None:
            return  # plain Postgres — keep regular table
        cur.execute('CREATE EXTENSION IF NOT EXISTS timescaledb')
        # PK must include the time partition column.
        cur.execute('ALTER TABLE attendance_events DROP CONSTRAINT IF EXISTS '
                    'attendance_events_pkey')
        cur.execute('ALTER TABLE attendance_events ADD PRIMARY KEY (id, "time")')
        cur.execute("SELECT create_hypertable('attendance_events', 'time', "
                    "chunk_time_interval => INTERVAL '7 days', "
                    "if_not_exists => TRUE, migrate_data => TRUE)")


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(make_hypertable, reverse_noop),
    ]
