#!/usr/bin/env python3
"""Test script to verify login functionality and database state."""

import sys
sys.path.insert(0, ".")

from db import engine, get_user_by_username
from password_utils import hash_password, verify_password
from sqlalchemy import text

def test_users_in_db():
    """Check if default users exist in database."""
    print("=" * 60)
    print("CHECKING USERS IN DATABASE")
    print("=" * 60)
    
    with engine.begin() as conn:
        result = conn.execute(text("SELECT id, username, role, full_name FROM users"))
        rows = result.fetchall()
        
        if not rows:
            print("❌ NO USERS FOUND IN DATABASE!")
            return False
        
        print(f"✅ Found {len(rows)} users in database:")
        for row in rows:
            print(f"   - ID: {row[0]}, Username: {row[1]}, Role: {row[2]}, Full Name: {row[3]}")
    
    return True

def test_password_hashing():
    """Test password hashing and verification."""
    print("\n" + "=" * 60)
    print("TESTING PASSWORD HASHING")
    print("=" * 60)
    
    test_password = "admin123"
    hashed = hash_password(test_password)
    print(f"Original password: {test_password}")
    print(f"Hashed password: {hashed}")
    
    # Test verification
    is_valid = verify_password(test_password, hashed)
    print(f"Password verification: {'✅ PASS' if is_valid else '❌ FAIL'}")
    
    return is_valid

def test_login():
    """Test login with admin credentials."""
    print("\n" + "=" * 60)
    print("TESTING LOGIN WITH ADMIN CREDENTIALS")
    print("=" * 60)
    
    username = "admin"
    password = "admin123"
    
    user = get_user_by_username(username)
    
    if not user:
        print(f"❌ User '{username}' not found in database")
        return False
    
    print(f"✅ User found: {user}")
    
    # Test password
    password_hash = user.get("password_hash")
    if not password_hash:
        print("❌ User has no password hash!")
        return False
    
    is_valid = verify_password(password, password_hash)
    
    if is_valid:
        print(f"✅ Password verification PASSED")
    else:
        print(f"❌ Password verification FAILED")
        print(f"   Expected password: {password}")
        print(f"   Hash in DB: {password_hash}")
    
    return is_valid

if __name__ == "__main__":
    try:
        users_ok = test_users_in_db()
        hash_ok = test_password_hashing()
        login_ok = test_login()
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Users in DB: {'✅' if users_ok else '❌'}")
        print(f"Password hashing: {'✅' if hash_ok else '❌'}")
        print(f"Login test: {'✅' if login_ok else '❌'}")
        
        if users_ok and hash_ok and login_ok:
            print("\n✅ ALL TESTS PASSED!")
        else:
            print("\n❌ SOME TESTS FAILED")
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
