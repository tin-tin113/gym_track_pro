from __future__ import annotations

from types import SimpleNamespace

from django.middleware.csrf import get_token


def _sidebar_state(request):
    resolver_match = getattr(request, "resolver_match", None)
    current_route = getattr(resolver_match, "view_name", "") or ""

    route_groups = [
        ({"member.member_dashboard"}, "member.dashboard", "Progress"),
        ({"member.member_profile", "member.edit_member_profile"}, "member.profile", "Profile"),
        (
            {"member.list_workouts", "member.workout_form", "member.create_workout", "member.edit_workout", "member.delete_workout"},
            "member.workouts",
            "Workouts",
        ),
        (
            {"member.member_programs", "member.browse_guides_library", "member.view_assigned_guide", "member.request_guide_assignment", "member.complete_guide"},
            "member.programs",
            "Guides & Programs",
        ),
        ({"member.current_diet", "member.log_meal", "member.diet_progress", "member.diet_history"}, "member.nutrition", "Nutrition"),
        ({"attendance_routes.check_in", "attendance_routes.undo_check_in"}, "attendance.check_in", "Check In"),
        (
            {
                "attendance_routes.dashboard",
                "attendance_routes.check_out",
                "attendance_routes.history",
            },
            "attendance.dashboard",
            "Attendance",
        ),
        ({"fitness.add_metrics"}, "fitness.metrics", "Metrics"),
        ({"trainer.dashboard"}, "trainer.dashboard", "Dashboard"),
        ({"trainer.members", "trainer.member_progress", "trainer.member_workouts", "trainer.assign_workout", "trainer.edit_assigned_workout", "trainer.delete_assigned_workout", "trainer.member_guides", "trainer.assign_guide_to_member", "trainer.unassign_guide", "trainer.member_diet", "trainer.assign_diet_to_member", "trainer.remove_member_diet"}, "trainer.members", "Members"),
        ({"trainer.list_guides", "trainer.browse_guides", "trainer.create_guide", "trainer.view_guide", "trainer.edit_guide", "trainer.delete_guide", "trainer.submit_guide", "trainer.add_guide_tip", "trainer.delete_guide_tip", "trainer.complete_member_guide"}, "trainer.guides", "Guides"),
        ({"trainer.list_diet_plans", "trainer.view_diet_plan"}, "trainer.diets", "Diets"),
        ({"trainer.list_trainers", "trainer.create_trainer", "trainer.edit_trainer", "trainer.manage_assignments", "trainer.delete_trainer", "trainer.resend_setup_link"}, "admin.trainers", "Trainers"),
        ({"staff.list_staff", "staff.create_staff", "staff.edit_staff", "staff.delete_staff"}, "admin.staff", "Staff"),
        ({"admin.dashboard"}, "admin.dashboard", "Dashboard"),
        ({"staff.dashboard"}, "staff.dashboard", "Dashboard"),
        ({"member.list_members", "member.create_member", "member.import_csv", "member.view_member", "member.edit_member", "member.assign_trainer", "admin.approve_member", "admin.reject_member"}, "admin.members", "Members"),
        ({"admin.pending_approvals"}, "admin.pending_approvals", "Pending Approvals"),
        ({"admin.pending_guides", "admin.all_guides", "admin.review_guide", "admin.approve_guide", "admin.reject_guide"}, "admin.pending_guides", "Guide Approvals"),
        ({"reports.daily_attendance"}, "reports.daily_attendance", "Today"),
        ({"reports.dashboard", "reports.attendance_report", "reports.fitness_report", "reports.fitness_export"}, "reports.dashboard", "Reports"),
    ]

    for route_names, active_route, label in route_groups:
        if current_route in route_names:
            return active_route, label

    return "", ""


def template_compat(request):
    # Provide a few legacy template aliases.
    # - request.args -> querystring
    # - request.form -> post body (or empty-ish on GET)
    try:
        setattr(request, 'args', request.GET)
        setattr(request, 'form', request.POST if request.method == 'POST' else request.GET)
    except Exception:
        # Extremely defensive: never break rendering if request is immutable.
        pass

    sidebar_active_route, sidebar_current_page_title = _sidebar_state(request)

    return {
        "current_user": getattr(request, "user", None),
        "csrf_token": get_token(request),
        "SimpleNamespace": SimpleNamespace,
        "sidebar_active_route": sidebar_active_route,
        "sidebar_current_page_title": sidebar_current_page_title,
    }
