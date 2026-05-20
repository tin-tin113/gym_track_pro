from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tracker.models import Member, Trainer, TrainerAssignment


class Command(BaseCommand):
    help = "Seed demo users (admin/staff/trainer/member)"

    def handle(self, *args, **options):
        User = get_user_model()

        def upsert_user(
            *,
            email: str,
            username: str,
            role: str,
            full_name: str,
            password: str,
            is_superuser: bool = False,
            is_staff: bool = False,
        ):
            user = User.objects.filter(email__iexact=email).first() or User.objects.filter(username=username).first()
            created = user is None

            if user is None:
                user = User(username=username, email=email)

            user.is_active = True
            user.is_superuser = bool(is_superuser)
            user.is_staff = bool(is_staff)
            if hasattr(user, "role"):
                user.role = role
            if hasattr(user, "full_name"):
                user.full_name = full_name

            user.set_password(password)
            user.save()
            return user, created

        password = "password123"
        today = timezone.localdate()

        with transaction.atomic():
            admin, admin_created = upsert_user(
                email="admin@gym.local",
                username="admin",
                role="admin",
                full_name="Administrator",
                password=password,
                is_superuser=True,
                is_staff=True,
            )

            staff, staff_created = upsert_user(
                email="staff@gym.local",
                username="staff",
                role="staff",
                full_name="Demo Staff",
                password=password,
                is_superuser=False,
				is_staff=True,
            )

            trainer_user, trainer_created = upsert_user(
                email="trainer@gym.local",
                username="trainer",
                role="trainer",
                full_name="Demo Trainer",
                password=password,
                is_superuser=False,
                is_staff=False,
            )
            Trainer.objects.get_or_create(user=trainer_user, defaults={"max_clients": 10})

            member_user, member_created = upsert_user(
                email="member@gym.local",
                username="member",
                role="member",
                full_name="Demo Member",
                password=password,
                is_superuser=False,
                is_staff=False,
            )

            member, _ = Member.objects.get_or_create(
                user=member_user,
                defaults={
                    "membership_start_date": today,
                    "membership_expiry_date": today + timedelta(days=30),
                    "is_active": True,
                    "is_approved": True,
                    "approval_date": timezone.now(),
                    "assigned_trainer": trainer_user,
                },
            )
            # Ensure assignment points to trainer
            if member.assigned_trainer_id != trainer_user.id:
                member.assigned_trainer = trainer_user
                member.save(update_fields=["assigned_trainer"])

            has_active = TrainerAssignment.objects.filter(member=member, is_active=True).exists()
            if not has_active:
                TrainerAssignment.objects.create(
                    trainer=trainer_user,
                    member=member,
                    assignment_date=today,
                    start_date=today,
                    assignment_type=TrainerAssignment.AssignmentType.PRIMARY,
                    is_active=True,
                )

        def _msg(created: bool, label: str, email: str):
            return f"{'Created' if created else 'Updated'} {label}: {email} / {password}"

        self.stdout.write(self.style.SUCCESS(_msg(admin_created, "admin", "admin@gym.local")))
        self.stdout.write(self.style.SUCCESS(_msg(staff_created, "staff", "staff@gym.local")))
        self.stdout.write(self.style.SUCCESS(_msg(trainer_created, "trainer", "trainer@gym.local")))
        self.stdout.write(self.style.SUCCESS(_msg(member_created, "member", "member@gym.local")))
