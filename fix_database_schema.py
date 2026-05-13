#!/usr/bin/env python
"""
Database schema migration script to add missing columns to existing tables.
Run this to fix schema mismatches in an existing database.
"""

import sqlite3
from pathlib import Path

def fix_database_schema():
    """Add missing columns to existing database tables."""

    db_path = Path(__file__).parent / 'instance' / 'gym_track.db'

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        print(f"Connecting to database: {db_path}")
        print()

        # Get existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Found tables: {tables}")
        print()

        # Fix users table
        if 'users' in tables:
            print("Checking users table...")
            cursor.execute("PRAGMA table_info(users)")
            columns = {row[1] for row in cursor.fetchall()}

            if 'setup_token' not in columns:
                print("  - Adding setup_token column...")
                try:
                    # Add without UNIQUE constraint (SQLite limitation with NULL values)
                    cursor.execute('ALTER TABLE users ADD COLUMN setup_token VARCHAR(255)')
                    conn.commit()
                    print("    [DONE] setup_token column added")
                except sqlite3.OperationalError as e:
                    if 'duplicate column' not in str(e).lower():
                        print(f"    [ERROR] {e}")
            else:
                print("  - setup_token column already exists")

            if 'setup_token_expiry' not in columns:
                print("  - Adding setup_token_expiry column...")
                try:
                    cursor.execute('ALTER TABLE users ADD COLUMN setup_token_expiry DATETIME')
                    conn.commit()
                    print("    [DONE] setup_token_expiry column added")
                except sqlite3.OperationalError as e:
                    if 'duplicate column' not in str(e).lower():
                        print(f"    [ERROR] {e}")
            else:
                print("  - setup_token_expiry column already exists")

        print()

        # Fix members table
        if 'members' in tables:
            print("Checking members table...")
            cursor.execute("PRAGMA table_info(members)")
            columns = {row[1] for row in cursor.fetchall()}

            if 'is_approved' not in columns:
                print("  - Adding is_approved column...")
                try:
                    cursor.execute('ALTER TABLE members ADD COLUMN is_approved BOOLEAN DEFAULT 0')
                    conn.commit()
                    print("    ✓ is_approved column added")
                except sqlite3.OperationalError as e:
                    if 'duplicate column' not in str(e).lower():
                        print(f"    ✗ Error: {e}")
            else:
                print("  - is_approved column already exists")

            if 'approval_date' not in columns:
                print("  - Adding approval_date column...")
                try:
                    cursor.execute('ALTER TABLE members ADD COLUMN approval_date DATETIME')
                    conn.commit()
                    print("    ✓ approval_date column added")
                except sqlite3.OperationalError as e:
                    if 'duplicate column' not in str(e).lower():
                        print(f"    ✗ Error: {e}")
            else:
                print("  - approval_date column already exists")

        print()
        print("[SUCCESS] Database schema migration complete!")
        conn.close()
        return True

    except Exception as e:
        print(f"[ERROR] Error during migration: {e}")
        return False

if __name__ == '__main__':
    fix_database_schema()
