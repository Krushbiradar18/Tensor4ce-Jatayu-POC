#!/usr/bin/env python3
"""Fix the users table schema."""

import sys
sys.path.insert(0, ".")

from db import engine
from sqlalchemy import text

print("Dropping old users table...")
with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
    print("✅ Old users table dropped")

print("\nCreating new users table with correct schema...")
with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'officer',
            full_name VARCHAR(255) DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    print("✅ New users table created")

print("\nSeeding default users...")
from password_utils import hash_password

users = [
    {"username": "admin", "password": "admin123", "role": "admin", "full_name": "Admin Officer"},
    {"username": "officer1", "password": "password", "role": "officer", "full_name": "Loan Officer"},
    {"username": "so1", "password": "password", "role": "senior_officer", "full_name": "Senior Officer"},
]

with engine.begin() as conn:
    for user in users:
        conn.execute(text("""
            INSERT INTO users (username, password_hash, role, full_name)
            VALUES (:username, :password_hash, :role, :full_name)
        """), {
            "username": user["username"],
            "password_hash": hash_password(user["password"]),
            "role": user["role"],
            "full_name": user["full_name"],
        })
        print(f"✅ Created user: {user['username']} / {user['password']}")

print("\n" + "=" * 60)
print("Database fix complete! Restart the backend server now.")
print("=" * 60)
