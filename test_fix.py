#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test if the database columns were added correctly."""

import sys
from app import create_app, db
from app.models.user import User

# Create app context
app = create_app('development')

with app.app_context():
    try:
        # Try to query a user - this will fail if setup_token columns don't exist
        user = User.query.first()

        if user:
            print("[OK] User retrieved successfully: {}".format(user.username))
            print("[OK] User has setup_token: {}".format(hasattr(user, 'setup_token')))
            print("[OK] User has setup_token_expiry: {}".format(hasattr(user, 'setup_token_expiry')))
            print("[OK] setup_token value: {}".format(user.setup_token))
            print("[OK] setup_token_expiry value: {}".format(user.setup_token_expiry))
            print("\n[SUCCESS] Database columns are working!")
        else:
            print("[OK] No users in database yet (this is OK)")
            print("[OK] Database columns exist and are accessible")
            print("\n[SUCCESS] Database columns are working!")

    except Exception as e:
        print("[ERROR] {}".format(e))
        print("\nThe database columns may not have been created yet.")
        print("Error details: {}".format(str(e)))
        sys.exit(1)
