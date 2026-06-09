from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),

    # Auth (matches Flask endpoints used in templates)
    path('auth/login', views.auth_login, name='auth.login'),
    path('auth/logout', views.auth_logout, name='auth.logout'),
    path('auth/profile', views.auth_profile, name='auth.profile'),
    path('auth/signup', views.auth_signup, name='auth.signup'),
    path('auth/register', views.auth_register, name='auth.register'),
    path('auth/pending', views.auth_pending_status, name='auth.pending_status'),
    path('auth/setup-password', views.auth_setup_password, name='auth.setup_password'),

    # Member
    path('members/', views.member_list_members, name='member.list_members'),
    path('members/new', views.member_create_member, name='member.create_member'),
    path('members/<int:member_id>', views.member_detail, name='member.view_member'),
    path('members/<int:member_id>/edit', views.member_edit, name='member.edit_member'),
    path('members/<int:member_id>/assign-trainer', views.member_assign_trainer, name='member.assign_trainer'),
    path('members/<int:member_id>/change-password', views.member_change_password, name='member.change_password'),

    # Member dashboard
    path('member/dashboard', views.member_dashboard, name='member.member_dashboard'),
    path('member/profile', views.member_profile, name='member.member_profile'),
    path('member/profile/edit', views.member_profile_edit, name='member.edit_member_profile'),
    path('member/workouts', views.member_workouts, name='member.list_workouts'),
    path('member/workouts/new', views.member_workout_form, name='member.workout_form'),
    path('member/workouts/new', views.member_workout_form, name='member.create_workout'),
    path('member/workouts/<int:workout_id>/edit', views.member_edit_workout, name='member.edit_workout'),
    path('member/workouts/<int:workout_id>/delete', views.member_delete_workout, name='member.delete_workout'),
    path('member/workouts/history', views.member_exercise_history, name='member.exercise_history'),
    path('member/programs', views.member_programs, name='member.member_programs'),
    path('member/programs/start-guide/<int:assignment_id>', views.start_assigned_guide_session, name='member.start_assigned_guide_session'),
    path('member/diet/current', views.member_current_diet, name='member.current_diet'),
    path('member/diet/log-meal', views.member_log_meal, name='member.log_meal'),
    path('member/diet/progress', views.member_diet_progress, name='member.diet_progress'),
    path('member/diet/history', views.member_diet_history, name='member.diet_history'),

    path('member/guides/library', views.member_guides_library, name='member.browse_guides_library'),
    path('member/guides/<int:guide_id>', views.member_view_assigned_guide, name='member.view_assigned_guide'),
    path('member/renew', views.member_renew, name='member.renew'),
    path('members/<int:member_id>/approve-renewal', views.member_approve_renewal, name='member.approve_renewal'),
    path('members/<int:member_id>/reject-renewal', views.member_reject_renewal, name='member.reject_renewal'),


    # Attendance
    path('attendance/', views.attendance_dashboard, name='attendance_routes.dashboard'),
    path('attendance/check-in', views.attendance_check_in, name='attendance_routes.check_in'),
    path('attendance/guest/new', views.attendance_log_guest, name='attendance_routes.log_guest'),
    path('attendance/undo-check-in', views.attendance_undo_check_in, name='attendance_routes.undo_check_in'),
    path('attendance/check-out/<int:attendance_id>', views.attendance_check_out, name='attendance_routes.check_out'),
    path('attendance/history', views.attendance_history, name='attendance_routes.history'),
    path('attendance/api/active-today', views.attendance_api_active_today, name='attendance_routes.api_active_today'),
    path('attendance/api/check-out/<int:attendance_id>', views.attendance_api_check_out, name='attendance_routes.api_check_out'),
    path('attendance/api/stats', views.attendance_api_stats, name='attendance_routes.api_stats'),
    path('attendance/guests/export-csv', views.attendance_export_guests_csv, name='attendance_routes.export_guests_csv'),

    # Fitness
    path('fitness/metrics', views.fitness_metrics, name='fitness.add_metrics'),

    # Trainer
    path('trainer/dashboard', views.trainer_dashboard, name='trainer.dashboard'),
    path('trainer/members', views.trainer_members, name='trainer.members'),
    path('trainer/list', views.trainer_list, name='trainer.list_trainers'),
    path('trainer/guides', views.trainer_guides, name='trainer.list_guides'),
    path('trainer/diets', views.trainer_diets, name='trainer.list_diet_plans'),

    # Trainer management (admin)
    path('trainer/new', views.trainer_create_trainer, name='trainer.create_trainer'),
    path('trainer/<int:trainer_id>/edit', views.trainer_edit_trainer, name='trainer.edit_trainer'),
    path('trainer/<int:trainer_id>/assignments', views.trainer_manage_assignments, name='trainer.manage_assignments'),
    path('trainer/<int:trainer_id>/delete', views.trainer_delete_trainer, name='trainer.delete_trainer'),
    path('trainer/<int:trainer_id>/reactivate', views.trainer_reactivate_trainer, name='trainer.reactivate_trainer'),
    path('trainer/<int:trainer_id>/resend-setup', views.trainer_resend_setup_link, name='trainer.resend_setup_link'),

    # Trainer member details
    path('trainer/members/<int:member_id>/progress', views.trainer_member_progress, name='trainer.member_progress'),
    path('trainer/members/<int:member_id>/workouts', views.trainer_member_workouts, name='trainer.member_workouts'),
    path('trainer/members/<int:member_id>/workouts/assign', views.trainer_assign_workout, name='trainer.assign_workout'),
    path('trainer/members/<int:member_id>/workouts/<int:workout_id>/edit', views.trainer_edit_assigned_workout, name='trainer.edit_assigned_workout'),
    path('trainer/members/<int:member_id>/workouts/<int:workout_id>/delete', views.trainer_delete_assigned_workout, name='trainer.delete_assigned_workout'),
    path('trainer/members/<int:member_id>/workouts/<int:workout_id>/set-notes', views.trainer_add_set_notes, name='trainer.add_set_notes'),

    # Guides
    path('trainer/guides/library', views.trainer_browse_guides, name='trainer.browse_guides'),
    path('trainer/guides/new', views.trainer_create_guide, name='trainer.create_guide'),
    path('trainer/guides/<int:guide_id>', views.trainer_view_guide, name='trainer.view_guide'),
    path('trainer/guides/<int:guide_id>/edit', views.trainer_edit_guide, name='trainer.edit_guide'),
    path('trainer/guides/<int:guide_id>/delete', views.trainer_delete_guide, name='trainer.delete_guide'),
    path('trainer/guides/<int:guide_id>/submit', views.trainer_submit_guide, name='trainer.submit_guide'),
    path('trainer/guides/<int:guide_id>/tips', views.trainer_add_guide_tip, name='trainer.add_guide_tip'),
    path('trainer/guides/<int:guide_id>/tips/<int:tip_id>/delete', views.trainer_delete_guide_tip, name='trainer.delete_guide_tip'),

    path('trainer/members/<int:member_id>/guides', views.trainer_member_guides, name='trainer.member_guides'),
    path('trainer/members/<int:member_id>/guides/assign', views.trainer_assign_guide_to_member, name='trainer.assign_guide_to_member'),
    path('trainer/members/<int:member_id>/guides/<int:guide_id>/unassign', views.trainer_unassign_guide, name='trainer.unassign_guide'),
    path('member/guides/<int:assignment_id>/complete', views.member_complete_guide, name='member.complete_guide'),
    path('trainer/guides/<int:assignment_id>/complete', views.trainer_complete_member_guide, name='trainer.complete_member_guide'),

    # Diets
    path('trainer/diets/new', views.trainer_create_diet_plan, name='trainer.create_diet_plan'),
    path('trainer/diets/<int:plan_id>', views.trainer_view_diet_plan, name='trainer.view_diet_plan'),
    path('trainer/diets/<int:plan_id>/edit', views.trainer_edit_diet_plan, name='trainer.edit_diet_plan'),
    path('trainer/diets/<int:plan_id>/delete', views.trainer_delete_diet_plan, name='trainer.delete_diet_plan'),
    path('trainer/diets/<int:plan_id>/meals/new', views.trainer_add_meal, name='trainer.add_meal'),
    path('trainer/diets/<int:plan_id>/meals/<int:meal_id>/delete', views.trainer_delete_meal, name='trainer.delete_meal'),
    path('trainer/members/<int:member_id>/diet', views.trainer_member_diet, name='trainer.member_diet'),
    path('trainer/members/<int:member_id>/diet/assign', views.trainer_assign_diet_to_member, name='trainer.assign_diet_to_member'),
    path('trainer/members/<int:member_id>/diet/remove', views.trainer_remove_member_diet, name='trainer.remove_member_diet'),

    # Staff
    path('staff/', views.staff_list, name='staff.list_staff'),
    path('staff/dashboard', views.staff_dashboard, name='staff.dashboard'),
    path('staff/new', views.staff_create_staff, name='staff.create_staff'),
    path('staff/<int:staff_id>/edit', views.staff_edit_staff, name='staff.edit_staff'),
    path('staff/<int:staff_id>/delete', views.staff_delete_staff, name='staff.delete_staff'),
    path('staff/<int:staff_id>/reactivate', views.staff_reactivate_staff, name='staff.reactivate_staff'),

    # Admin (custom dashboard pages, separate from Django admin site)
    path('admin/dashboard', views.admin_dashboard, name='admin.dashboard'),
    path('admin/pending-approvals', views.admin_pending_approvals, name='admin.pending_approvals'),
    path('admin/members/<int:member_id>/approve', views.admin_approve_member, name='admin.approve_member'),
    path('admin/members/<int:member_id>/reject', views.admin_reject_member, name='admin.reject_member'),
    path('admin/pending-guides', views.admin_pending_guides, name='admin.pending_guides'),
    path('admin/all-guides', views.admin_all_guides, name='admin.all_guides'),
    path('admin/guides/<int:guide_id>/review', views.admin_review_guide, name='admin.review_guide'),
    path('admin/guides/<int:guide_id>/approve', views.admin_approve_guide, name='admin.approve_guide'),
    path('admin/guides/<int:guide_id>/reject', views.admin_reject_guide, name='admin.reject_guide'),

    # Reports
    path('reports/', views.reports_dashboard, name='reports.dashboard'),
    path('reports/daily-attendance', views.reports_daily_attendance, name='reports.daily_attendance'),
    path('reports/attendance-report', views.reports_attendance_report, name='reports.attendance_report'),
    path('reports/fitness/<int:member_id>', views.reports_fitness_report, name='reports.fitness_report'),
    path('reports/fitness/<int:member_id>/export', views.reports_fitness_export, name='reports.fitness_export'),

    # API
    path('api/health', views.api_health, name='api.health'),
]
