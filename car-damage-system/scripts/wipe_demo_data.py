"""One-off: wipe all demo data from the production database so it can be
reseeded cleanly. Truncates vehicles + webhook_registrations, which
cascades to scans/scan_images/damage_records/damage_diffs/alert_logs via
their foreign keys. Leaves schema, migrations, and the (unused) users
table untouched.

Usage:
    python scripts/wipe_demo_data.py "postgresql://user:pass@host/dbname"
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg


async def main(database_url: str) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        before = {
            t: await conn.fetchval(f"SELECT count(*) FROM {t}")
            for t in ["vehicles", "scans", "scan_images", "damage_records", "damage_diffs", "alert_logs", "webhook_registrations"]
        }
        print("Before:", before)

        await conn.execute("TRUNCATE vehicles, webhook_registrations CASCADE;")

        after = {
            t: await conn.fetchval(f"SELECT count(*) FROM {t}")
            for t in before
        }
        print("After:", after)
        print("Wiped clean.")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/wipe_demo_data.py <database_url>")
    asyncio.run(main(sys.argv[1]))
