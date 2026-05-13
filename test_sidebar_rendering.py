#!/usr/bin/env python
"""Test sidebar rendering on actual application pages."""

from app import create_app
from unittest.mock import Mock, patch
from flask_login import current_user

app = create_app()

print("\n" + "="*70)
print("SIDEBAR RENDERING TEST - SIMULATED PAGE LOADS")
print("="*70 + "\n")

# Test different page scenarios
test_scenarios = [
    {
        'name': 'Unauthenticated User (Login Page)',
        'user': None,
        'is_authenticated': False,
        'is_admin': False,
        'is_staff': False,
        'member': None,
        'trainer': None,
        'description': 'Sidebar should NOT appear'
    },
    {
        'name': 'Member User (Dashboard)',
        'user': 'test_member',
        'is_authenticated': True,
        'is_admin': False,
        'is_staff': False,
        'member': True,
        'trainer': None,
        'description': 'Sidebar WITH member navigation'
    },
    {
        'name': 'Trainer User (Dashboard)',
        'user': 'test_trainer',
        'is_authenticated': True,
        'is_admin': False,
        'is_staff': False,
        'member': None,
        'trainer': True,
        'description': 'Sidebar WITH trainer navigation'
    },
    {
        'name': 'Admin User (Dashboard)',
        'user': 'test_admin',
        'is_authenticated': True,
        'is_admin': True,
        'is_staff': False,
        'member': None,
        'trainer': None,
        'description': 'Sidebar WITH admin navigation'
    },
    {
        'name': 'Staff User (Dashboard)',
        'user': 'test_staff',
        'is_authenticated': True,
        'is_admin': False,
        'is_staff': True,
        'member': None,
        'trainer': None,
        'description': 'Sidebar WITH staff navigation'
    }
]

def create_mock_user(scenario):
    """Create a mock user for the test scenario."""
    if scenario['user'] is None:
        return None

    mock_user = Mock()
    mock_user.is_authenticated = scenario['is_authenticated']
    mock_user.is_admin = scenario['is_admin']
    mock_user.is_staff = scenario['is_staff']
    mock_user.is_active = True
    mock_user.member = scenario['member']
    mock_user.trainer = scenario['trainer']
    mock_user.full_name = scenario['name']
    return mock_user

with app.app_context():
    from flask import render_template_string
    from jinja2 import Environment, FileSystemLoader

    # Load templates
    env = Environment(loader=FileSystemLoader('app/templates'))
    base_template = env.get_template('base.html')

    results = []

    for idx, scenario in enumerate(test_scenarios, 1):
        print(f"[TEST {idx}] {scenario['name']}")
        print(f"  Description: {scenario['description']}")
        print("-" * 70)

        mock_user = create_mock_user(scenario)

        with app.test_request_context():
            # Create a mock current_user
            with patch('flask_login.current_user', mock_user or Mock(is_authenticated=False)):
                try:
                    # Render the template
                    from flask import render_template
                    rendered = render_template('base.html')

                    # Check expectations
                    has_sidebar = '<div class="sidebar">' in rendered
                    has_navbar = 'navbar' in rendered.lower()
                    page_valid = len(rendered) > 1000

                    if scenario['is_authenticated']:
                        # For authenticated users, sidebar SHOULD be present
                        sidebar_check = has_sidebar
                        expected = True
                    else:
                        # For unauthenticated users, sidebar should NOT be present
                        sidebar_check = not has_sidebar
                        expected = True

                    status = "PASS" if sidebar_check and page_valid else "FAIL"
                    results.append((scenario['name'], status))

                    print(f"  [PASS] Page renders ({len(rendered)} chars)")
                    print(f"  [{'PASS' if has_navbar else 'FAIL'}] Navbar present")
                    print(f"  [{'PASS' if has_sidebar else 'FAIL'}] Sidebar present: {has_sidebar}")

                    if scenario['is_authenticated']:
                        # Check for specific navigation items
                        if scenario['member']:
                            member_nav = 'member.member_dashboard' not in rendered and 'My Progress' in rendered
                            print(f"  [{'PASS' if member_nav else 'FAIL'}] Member navigation visible")
                        elif scenario['trainer']:
                            trainer_nav = 'trainer.dashboard' not in rendered and 'Dashboard' in rendered
                            print(f"  [{'PASS' if trainer_nav else 'FAIL'}] Trainer navigation visible")
                        elif scenario['is_admin']:
                            admin_nav = 'admin.dashboard' not in rendered and 'Dashboard' in rendered
                            print(f"  [{'PASS' if admin_nav else 'FAIL'}] Admin navigation visible")
                        elif scenario['is_staff']:
                            staff_nav = 'Manage Members' in rendered or 'Dashboard' in rendered
                            print(f"  [{'PASS' if staff_nav else 'FAIL'}] Staff navigation visible")

                except Exception as e:
                    print(f"  [FAIL] Render error: {str(e)[:100]}")
                    results.append((scenario['name'], "FAIL"))

        print()

    # Summary
    print("="*70)
    print("RENDERING TEST SUMMARY")
    print("="*70)

    passes = sum(1 for _, status in results if status == "PASS")
    total = len(results)

    print(f"\nPassed: {passes}/{total}")
    print("\nResults:")
    for name, status in results:
        icon = "[PASS]" if status == "PASS" else "[FAIL]"
        print(f"  {icon} {name}")

    overall_status = "ALL TESTS PASSED" if passes == total else f"SOME TESTS FAILED ({total - passes} failures)"
    print(f"\nOverall Status: {overall_status}")

    print("\n" + "="*70 + "\n")
