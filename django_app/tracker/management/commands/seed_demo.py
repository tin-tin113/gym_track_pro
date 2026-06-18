from __future__ import annotations

import random
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tracker.models import (
    Member, Trainer, TrainerAssignment, Attendance, FitnessMetric,
    Workout, WorkoutSet, DietPlan, MealPlan, DietAssignment, MealLog, GuestVisit
)


class Command(BaseCommand):
    help = "Seed realistic data (users, members, attendance, workouts, diets, guests)"

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

        password = "P@ssw0rd"
        today = timezone.localdate()

        with transaction.atomic():
            # Deleting existing mock/demo data to avoid duplicates if re-run on dirty DB
            # (though the user will typically reset, clean up ensures safety)
            Attendance.objects.all().delete()
            FitnessMetric.objects.all().delete()
            WorkoutSet.objects.all().delete()
            Workout.objects.all().delete()
            MealLog.objects.all().delete()
            DietAssignment.objects.all().delete()
            MealPlan.objects.all().delete()
            DietPlan.objects.all().delete()
            GuestVisit.objects.all().delete()

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
                full_name="Staff",
                password=password,
                is_superuser=False,
                is_staff=True,
            )

            trainer_user, trainer_created = upsert_user(
                email="trainer@gym.local",
                username="trainer",
                role="trainer",
                full_name="Trainer",
                password=password,
                is_superuser=False,
                is_staff=False,
            )
            Trainer.objects.get_or_create(user=trainer_user, defaults={"max_clients": 10})

            # Seed 5 members
            members_data = [
                ("member@gym.local", "member", "Member One", 80.0, 175.0),
                ("member2@gym.local", "member2", "Member Two", 95.0, 180.0),
                ("member3@gym.local", "member3", "Member Three", 65.0, 165.0),
                ("member4@gym.local", "member4", "Member Four", 70.0, 170.0),
                ("member5@gym.local", "member5", "Member Five", 110.0, 185.0),
            ]

            member_results = []
            for email, username, full_name, initial_weight, height in members_data:
                m_user, m_created = upsert_user(
                    email=email,
                    username=username,
                    role="member",
                    full_name=full_name,
                    password=password,
                    is_superuser=False,
                    is_staff=False,
                )

                member, _ = Member.objects.get_or_create(
                    user=m_user,
                    defaults={
                        "membership_start_date": today - timedelta(days=15),
                        "membership_expiry_date": today + timedelta(days=15),
                        "is_active": True,
                        "is_approved": True,
                        "approval_date": timezone.now() - timedelta(days=15),
                        "assigned_trainer": trainer_user,
                    },
                )
                # Ensure assignment points to trainer
                if member.assigned_trainer_id != trainer_user.id:
                    member.assigned_trainer = trainer_user
                    member.save(update_fields=["assigned_trainer"])

                TrainerAssignment.objects.filter(member=member, is_active=True).update(is_active=False)
                TrainerAssignment.objects.create(
                    trainer=trainer_user,
                    member=member,
                    assignment_date=today - timedelta(days=15),
                    start_date=today - timedelta(days=15),
                    assignment_type=TrainerAssignment.AssignmentType.PRIMARY,
                    is_active=True,
                )
                member_results.append((member, m_user, m_created, initial_weight, height))

            # Seed Attendance (historical visits over the last 14 days)
            for member, _, _, _, _ in member_results:
                # Let's seed 8 visits out of 14 days
                for i in range(14):
                    # Keep some random variation (e.g. check in every other day)
                    if (i + member.id) % 2 == 0:
                        visit_date = today - timedelta(days=i)
                        check_in_time = timezone.make_aware(
                            timezone.datetime.combine(visit_date, timezone.datetime.min.time()) + timedelta(hours=8, minutes=random.randint(0, 59))
                        )
                        check_out_time = check_in_time + timedelta(minutes=random.randint(45, 90))
                        Attendance.objects.create(
                            member=member,
                            check_in_time=check_in_time,
                            check_out_time=check_out_time,
                            duration_minutes=(check_out_time - check_in_time).seconds // 60,
                            qr_code=f"QR-{member.id}-{i}-{random.randint(1000, 9999)}",
                        )

            # Seed FitnessMetrics (Weight progress over the last 30 days)
            for member, _, _, initial_weight, height in member_results:
                for idx, days_ago in enumerate([20, 10, 0]):
                    metric_date = today - timedelta(days=days_ago)
                    # Weight decreases slightly for each check-in (realistic progress)
                    weight = initial_weight - (idx * 0.8)
                    height_m = height / 100.0
                    bmi = round(weight / (height_m * height_m), 2)
                    FitnessMetric.objects.create(
                        member=member,
                        metric_date=metric_date,
                        weight=weight,
                        height=height,
                        bmi=bmi,
                        chest=90.0 - (idx * 0.2),
                        waist=80.0 - (idx * 0.4),
                        hips=95.0 - (idx * 0.3),
                        bicep=32.0 + (idx * 0.1),
                        thigh=55.0 - (idx * 0.2),
                        body_fat_percentage=22.0 - (idx * 0.5),
                        muscle_mass=35.0 + (idx * 0.3),
                        created_by=trainer_user,
                        notes=f"Progress check at day {days_ago} ago."
                    )

            # Seed Workouts & Sets
            for member, _, _, _, _ in member_results:
                # 1. Chest Workout (Bench Press) 5 days ago
                w1 = Workout.objects.create(
                    member=member,
                    workout_date=today - timedelta(days=5),
                    exercise_name="Bench Press",
                    exercise_category="Strength",
                    muscle_group=Workout.MuscleGroup.CHEST,
                    sets=3,
                    reps=10,
                    weight=50.0,
                    intensity=Workout.Intensity.MODERATE,
                    notes="Felt good, solid push.",
                    trainer=trainer_user,
                    assigned_date=timezone.now() - timedelta(days=6)
                )
                for s in range(1, 4):
                    WorkoutSet.objects.create(
                        workout=w1,
                        set_number=s,
                        reps=10,
                        weight=40.0 + (s * 5),
                        is_completed=True,
                        is_pr=(s == 3)
                    )

                # 2. Leg Workout (Squats) 2 days ago
                w2 = Workout.objects.create(
                    member=member,
                    workout_date=today - timedelta(days=2),
                    exercise_name="Squats",
                    exercise_category="Strength",
                    muscle_group=Workout.MuscleGroup.LEGS,
                    sets=3,
                    reps=8,
                    weight=60.0,
                    intensity=Workout.Intensity.INTENSE,
                    notes="Deep squats, focus on posture.",
                    trainer=trainer_user,
                    assigned_date=timezone.now() - timedelta(days=3)
                )
                for s in range(1, 4):
                    WorkoutSet.objects.create(
                        workout=w2,
                        set_number=s,
                        reps=8,
                        weight=50.0 + (s * 5),
                        is_completed=True,
                        is_pr=(s == 3)
                    )

                # 3. Cardio Workout (Running) today
                Workout.objects.create(
                    member=member,
                    workout_date=today,
                    exercise_name="Outdoor Running",
                    exercise_category="Cardio",
                    muscle_group=Workout.MuscleGroup.CARDIO,
                    duration_minutes=30,
                    distance_km=5.0,
                    intensity=Workout.Intensity.MODERATE,
                    notes="30 min cardio run.",
                )

            # Seed DietPlans & MealPlans
            keto_plan = DietPlan.objects.create(
                name="Keto Shred",
                description="Low carb, high fat diet designed for fat loss and cognitive performance.",
                diet_type="Ketogenic",
                daily_calories=1800,
                macro_ratio_protein=0.25,
                macro_ratio_carbs=0.05,
                macro_ratio_fats=0.70,
                created_by=trainer_user,
            )
            keto_meals = [
                ("Breakfast", "Avocado & Scrambled Eggs in Butter", 500, 25, 4, 42),
                ("Lunch", "Grilled Salmon with Asparagus & Olive Oil", 650, 45, 6, 50),
                ("Dinner", "Ribeye Steak with Garlic Butter Broccoli", 650, 48, 5, 52),
            ]
            keto_meal_objs = []
            for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
                for m_type, m_name, cals, prot, carbs, fats in keto_meals:
                    m_plan = MealPlan.objects.create(
                        diet_plan=keto_plan,
                        day_name=day,
                        meal_type=m_type,
                        meal_name=m_name,
                        calories=cals,
                        protein_g=prot,
                        carbs_g=carbs,
                        fats_g=fats,
                    )
                    keto_meal_objs.append(m_plan)

            bulk_plan = DietPlan.objects.create(
                name="Lean Mass Gain",
                description="High protein, high carb diet targeting muscle hypertrophy and recovery.",
                diet_type="High Protein Bulk",
                daily_calories=2800,
                macro_ratio_protein=0.30,
                macro_ratio_carbs=0.50,
                macro_ratio_fats=0.20,
                created_by=trainer_user,
            )
            bulk_meals = [
                ("Breakfast", "Oatmeal with Whey Protein, Banana & Peanut Butter", 700, 45, 80, 20),
                ("Lunch", "Chicken Breast with Jasmine Rice & Broccoli", 900, 65, 110, 15),
                ("Dinner", "Lean Ground Beef with Sweet Potatoes & Green Beans", 900, 60, 100, 22),
                ("Snack", "Greek Yogurt with Mixed Berries & Almonds", 300, 25, 20, 10),
            ]
            bulk_meal_objs = []
            for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
                for m_type, m_name, cals, prot, carbs, fats in bulk_meals:
                    m_plan = MealPlan.objects.create(
                        diet_plan=bulk_plan,
                        day_name=day,
                        meal_type=m_type,
                        meal_name=m_name,
                        calories=cals,
                        protein_g=prot,
                        carbs_g=carbs,
                        fats_g=fats,
                    )
                    bulk_meal_objs.append(m_plan)

            # Assign Diet Plans and Log Meals
            for idx, (member, _, _, _, _) in enumerate(member_results):
                # Members 1-3 get Keto, 4-5 get Bulk
                plan = keto_plan if idx < 3 else bulk_plan
                meal_plans = keto_meal_objs if idx < 3 else bulk_meal_objs

                assignment = DietAssignment.objects.create(
                    diet_plan=plan,
                    member=member,
                    trainer=trainer_user,
                    assignment_date=timezone.now() - timedelta(days=10),
                    start_date=timezone.now() - timedelta(days=10),
                    target_end_date=timezone.now() + timedelta(days=20),
                    is_active=True,
                )

                # Log meals for yesterday and today
                for days_offset in [1, 0]:
                    log_date = today - timedelta(days=days_offset)
                    day_name = log_date.strftime('%A')
                    day_meal_plans = [mp for mp in meal_plans if mp.day_name == day_name]
                    for mp in day_meal_plans:
                        MealLog.objects.create(
                            member=member,
                            diet_assignment=assignment,
                            meal_plan=mp,
                            meal_date=log_date,
                            meal_type=mp.meal_type,
                            meal_name=mp.meal_name,
                            calories_actual=mp.calories + random.randint(-50, 50),
                            protein_g=mp.protein_g + random.randint(-5, 5),
                            carbs_g=mp.carbs_g + random.randint(-10, 10),
                            fats_g=mp.fats_g + random.randint(-5, 5),
                            notes="Logged from plan."
                        )

            # Seed Guest Visits
            # 3 guests today
            GuestVisit.objects.create(
                full_name="Alice Green",
                guest_type=GuestVisit.GuestType.REGULAR,
                email="alice@gmail.local",
                phone_number="555-0199",
                visit_date=today,
                amount_paid=100.0,
                emergency_contact="Bob Green (555-0198)",
                notes="First time trying the gym."
            )
            GuestVisit.objects.create(
                full_name="Charlie Brown",
                guest_type=GuestVisit.GuestType.STUDENT,
                email="charlie@school.local",
                phone_number="555-0200",
                visit_date=today,
                amount_paid=50.0,
                emergency_contact="Sally Brown (555-0201)",
                notes="Student single entry."
            )
            GuestVisit.objects.create(
                full_name="David Wright",
                guest_type=GuestVisit.GuestType.REGULAR,
                email="david@gmail.local",
                phone_number="555-0202",
                visit_date=today,
                amount_paid=100.0,
                emergency_contact="Eve Wright (555-0203)",
                notes="One-off visitor."
            )
            # 2 guests yesterday
            GuestVisit.objects.create(
                full_name="Fiona Miller",
                guest_type=GuestVisit.GuestType.REGULAR,
                email="fiona@gmail.local",
                phone_number="555-0204",
                visit_date=today - timedelta(days=1),
                amount_paid=100.0,
                emergency_contact="George Miller (555-0205)",
                notes="Single entry."
            )
            GuestVisit.objects.create(
                full_name="Harry Davis",
                guest_type=GuestVisit.GuestType.STUDENT,
                email="harry@school.local",
                phone_number="555-0206",
                visit_date=today - timedelta(days=1),
                amount_paid=50.0,
                emergency_contact="Ian Davis (555-0207)",
                notes="Student entry."
            )

        def _msg(created: bool, label: str, email: str):
            return f"{'Created' if created else 'Updated'} {label}: {email} / {password}"

        self.stdout.write(self.style.SUCCESS(_msg(admin_created, "admin", "admin@gym.local")))
        self.stdout.write(self.style.SUCCESS(_msg(staff_created, "staff", "staff@gym.local")))
        self.stdout.write(self.style.SUCCESS(_msg(trainer_created, "trainer", "trainer@gym.local")))
        for member, m_user, m_created, _, _ in member_results:
            self.stdout.write(self.style.SUCCESS(_msg(m_created, f"member ({m_user.full_name})", m_user.email)))
