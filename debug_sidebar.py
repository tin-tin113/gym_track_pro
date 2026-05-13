#!/usr/bin/env python
"""Debug sidebar rendering in actual Flask app."""

import os
from app import create_app, db
from app.models.user import User
from app.models.member import Member

app = create_app()

print("\n" + "="*70)
print("SIDEBAR RENDERING DEBUG - ACTUAL APPLICATION TEST")
print("="*70 + "\n")

with app.app_context():
    # Create test database
    db.create_all()

    # Create test user
    test_user = User.query.filter_by(email='test@test.com').first()
    if not test_user:
        test_user = User(
            email='test@test.com',
            full_name='Test User',
            password_hash='hashed_password',
            is_admin=False,
            is_approved=True,
            is_staff=False
        )
        db.session.add(test_user)
        db.session.commit()
        print(f"[DEBUG] Created test user: {test_user.email}")

    # Create member profile
    member = Member.query.filter_by(user_id=test_user.id).first()
    if not member:
        member = Member(
            user_id=test_user.id,
            membership_type='basic',
            membership_start='2026-01-01',
            membership_end='2026-12-31'
        )
        db.session.add(member)
        db.session.commit()
        print(f"[DEBUG] Created member profile for: {test_user.full_name}")

    # Test with actual test client
    client = app.test_client()

    print("\n[TEST 1] Testing unauthenticated access")
    print("-" * 70)
    response = client.get('/')
    print(f"Status: {response.status_code}")
    has_sidebar = b'class="sidebar"' in response.data
    has_auth_check = b'main' in response.data
    print(f"Sidebar in response: {has_sidebar}")
    print(f"Page renders: {len(response.data)} bytes")

    print("\n[TEST 2] Login and check authenticated pages")
    print("-" * 70)

    # Login
    login_data = {
        'email': 'test@test.com',
        'password': 'password'  # This will fail because password is hashed
    }
    login_response = client.post('/auth/login', data=login_data, follow_redirects=True)
    print(f"Login attempt status: {login_response.status_code}")

    print("\n[TEST 3] Check base.html template rendering")
    print("-" * 70)
    with app.test_request_context():
        from flask import render_template
        from flask_login import current_user

        # Check what base.html looks like
        with open('app/templates/base.html', 'r') as f:
            base_content = f.read()

        print(f"base.html lines: {len(base_content.splitlines())}")
        print(f"base.html size: {len(base_content)} bytes")

        # Look for sidebar include
        if "include 'sidebar.html'" in base_content:
            print("✅ Sidebar include found in base.html")
        else:
            print("❌ Sidebar include NOT found in base.html")

        # Look for authentication check
        if 'current_user.is_authenticated' in base_content:
            print("✅ Authentication check found")
        else:
            print("❌ Authentication check NOT found")

        # Show the relevant lines
        lines = base_content.splitlines()
        print("\nLines 58-65 of base.html:")
        for idx, line in enumerate(lines[57:65], 58):
            print(f"  {idx}: {line}")

    print("\n[TEST 4] Check sidebar.html template")
    print("-" * 70)
    with open('app/templates/sidebar.html', 'r') as f:
        sidebar_content = f.read()

    print(f"sidebar.html lines: {len(sidebar_content.splitlines())}")
    print(f"sidebar.html size: {len(sidebar_content)} bytes")

    # Look for role conditionals
    checks = [
        ('Member conditional', 'if current_user.member' in sidebar_content),
        ('Trainer conditional', 'if current_user.trainer' in sidebar_content),
        ('Admin conditional', 'if current_user.is_admin' in sidebar_content),
        ('Staff conditional', 'if current_user.is_staff' in sidebar_content),
        ('Sidebar div', '<div class="sidebar">' in sidebar_content),
    ]

    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"{status} {name}")

    print("\n[TEST 5] Check CSS file")
    print("-" * 70)
    if os.path.exists('app/static/css/design-system.css'):
        with open('app/static/css/design-system.css', 'r') as f:
            css_content = f.read()

        has_sidebar_css = '.sidebar' in css_content
        has_width = '280px' in css_content
        print(f"{'✅' if has_sidebar_css else '❌'} Sidebar CSS defined")
        print(f"{'✅' if has_width else '❌'} Sidebar width (280px) defined")
        print(f"CSS file size: {len(css_content)} bytes")
