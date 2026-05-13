#!/usr/bin/env python
"""Database migration script to add missing columns."""
import sqlite3
from pathlib import Path

db_path = Path('instance/gym_track.db')

if db_path.exists():
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check if columns exist
        cursor.execute("PRAGMA table_info(members)")
        columns = {row[1] for row in cursor.fetchall()}

        # Add missing columns if they don't exist
        if 'is_approved' not in columns:
            cursor.execute("ALTER TABLE members ADD COLUMN is_approved BOOLEAN DEFAULT 0 NOT NULL")
            print("[OK] Added is_approved column")

        if 'approval_date' not in columns:
            cursor.execute("ALTER TABLE members ADD COLUMN approval_date DATETIME")
            print("[OK] Added approval_date column")

        conn.commit()
        conn.close()
        print("[OK] Database migration successful!")
    except Exception as e:
        print(f"[ERROR] {e}")
        exit(1)
else:
    print("Database file not found - will be created on app startup")
