"""
Middleware to enforce is_active check on every request.

Purpose: Ensure deactivated staff/trainers are immediately logged out
if they try to access protected views with an existing session.
"""

from django.shortcuts import redirect
from django.contrib.auth import logout
from django.contrib import messages


class CheckActiveUserMiddleware:
    """
    Middleware that checks if an authenticated user's account is still active.

    If a user is logged in but has been deactivated (is_active=False),
    they are immediately logged out and redirected to login.

    This prevents deactivated staff/trainers from accessing views
    if they were online when their account was disabled.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if user is authenticated but account has been deactivated
        if request.user.is_authenticated and not request.user.is_active:
            # Log them out
            logout(request)
            messages.error(
                request,
                'Your account has been deactivated. Please contact the administrator.'
            )
            return redirect('auth.login')

        # Continue with normal request processing
        response = self.get_response(request)
        return response
