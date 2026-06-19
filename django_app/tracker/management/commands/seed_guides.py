from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from tracker.models import WorkoutGuide, WorkoutTip


class Command(BaseCommand):
    help = "Seed demo workout guides with exercise tips"

    def handle(self, *args, **options):
        User = get_user_model()

        # Get trainer user
        trainer = User.objects.filter(role='trainer').first()
        if not trainer:
            self.stdout.write(self.style.ERROR("No trainer found. Run 'seed_demo' first."))
            return

        # Define guides with tips
        guides_data = [
            {
                "name": "Beginner Full Body Strength",
                "description": "Complete full-body workout for beginners focusing on compound movements and building foundational strength.",
                "category": "Strength",
                "difficulty_level": "Beginner",
                "duration_weeks": 4,
                "target_goals": "Build Strength, Muscle Tone, Endurance",
                "equipment_needed": "Dumbbells, Barbell, Weight Bench",
                "tips": [
                    {"exercise_name": "Dumbbell Squats", "tip_category": "form", "content": "Keep your chest up and knees tracking over your toes. Squat down until your thighs are parallel to the ground. Engage your core throughout."},
                    {"exercise_name": "Dumbbell Squats", "tip_category": "recovery", "content": "Rest 60-90 seconds between sets. Quad soreness is normal; foam roll after workout."},
                    {"exercise_name": "Bench Press", "tip_category": "form", "content": "Lower the bar to your mid-chest, keep elbows at 45 degrees, press explosively back up. Full range of motion is key."},
                    {"exercise_name": "Bench Press", "tip_category": "nutrition", "content": "Consume protein within 30 minutes post-workout to support muscle recovery."},
                    {"exercise_name": "Bent Over Rows", "tip_category": "form", "content": "Hinge at hips, keep back straight, pull bar to ribcage. Control the negative portion of the movement."},
                ]
            },
            {
                "name": "Intermediate Push/Pull Split",
                "description": "Upper body split routine alternating push and pull movements for strength and muscle hypertrophy.",
                "category": "Strength",
                "difficulty_level": "Intermediate",
                "duration_weeks": 6,
                "target_goals": "Muscle Gain, Strength, Upper Body Power",
                "equipment_needed": "Dumbbells, Barbell, Cables, Pull-up Bar",
                "tips": [
                    {"exercise_name": "Incline Dumbbell Press", "tip_category": "form", "content": "Set bench to 45 degrees, press dumbbells up and slightly forward. Maintain stability and control."},
                    {"exercise_name": "Lat Pulldowns", "tip_category": "form", "content": "Pull elbows down and back, squeeze shoulder blades together. Avoid using momentum."},
                    {"exercise_name": "Landmine Rows", "tip_category": "recovery", "content": "Allows for a more natural grip. Excellent for reducing wrist strain during heavy rows."},
                    {"exercise_name": "Dips", "tip_category": "form", "content": "Lean forward slightly for chest activation. Lower until elbows are at 90 degrees."},
                    {"exercise_name": "Face Pulls", "tip_category": "mental", "content": "Focus on pulling the rope apart and feeling the rear deltoid contraction. Great for posture."},
                ]
            },
            {
                "name": "HIIT Cardio Blast",
                "description": "High-intensity interval training for maximum calorie burn and cardiovascular improvement in minimal time.",
                "category": "Cardio",
                "difficulty_level": "Intermediate",
                "duration_weeks": 4,
                "target_goals": "Fat Loss, Cardiovascular Endurance, Metabolism Boost",
                "equipment_needed": "Dumbbells, Jump Rope, Timer",
                "tips": [
                    {"exercise_name": "Burpees", "tip_category": "form", "content": "Jump back to plank, do a push-up, jump feet to hands, then jump up. Maintain intensity throughout."},
                    {"exercise_name": "Jump Rope", "tip_category": "form", "content": "Stay on the balls of your feet, keep elbows at 90 degrees, use wrist motion to spin the rope."},
                    {"exercise_name": "Mountain Climbers", "tip_category": "recovery", "content": "Active recovery between sets. Keep core engaged to protect lower back."},
                    {"exercise_name": "High Knees", "tip_category": "nutrition", "content": "HIIT workouts increase calorie burn for hours post-exercise. Stay hydrated and refuel with carbs."},
                    {"exercise_name": "Box Jumps", "tip_category": "form", "content": "Land softly on the balls of your feet, absorb impact with bent knees. Start with a lower box if needed."},
                ]
            },
            {
                "name": "Mind-Body Yoga Flow",
                "description": "Gentle yoga flow combining strength, flexibility, and mindfulness for holistic wellness.",
                "category": "Flexibility",
                "difficulty_level": "Beginner",
                "duration_weeks": 3,
                "target_goals": "Flexibility, Stress Relief, Balance",
                "equipment_needed": "Yoga Mat, Yoga Blocks, Yoga Strap",
                "tips": [
                    {"exercise_name": "Downward Dog", "tip_category": "form", "content": "Spread fingers wide, press palms into ground. Ears between arms, heels toward ground."},
                    {"exercise_name": "Warrior Flow", "tip_category": "mental", "content": "Move with intention and breath. Coordinate each movement with an inhale or exhale for flow."},
                    {"exercise_name": "Pigeon Pose", "tip_category": "recovery", "content": "Hold 5-7 breath cycles on each side. This deep hip opener aids recovery from lower body workouts."},
                    {"exercise_name": "Child's Pose", "tip_category": "form", "content": "Knees wide, big toes touching, sink hips to heels. Extend arms and relax forehead to mat."},
                    {"exercise_name": "Savasana", "tip_category": "mental", "content": "Rest 5-10 minutes at end. This integration period is where the real benefits consolidate."},
                ]
            },
            {
                "name": "CrossFit Fundamentals",
                "description": "Functional fitness training combining weightlifting, gymnastics, and metabolic conditioning.",
                "category": "Functional",
                "difficulty_level": "Advanced",
                "duration_weeks": 8,
                "target_goals": "Full Body Fitness, Power, Agility",
                "equipment_needed": "Barbell, Kettlebells, Pull-up Bar, Rope, Medicine Ball",
                "tips": [
                    {"exercise_name": "Clean and Jerk", "tip_category": "form", "content": "Explosive hip extension, catch in squat, press overhead with tight core. Mobility is essential."},
                    {"exercise_name": "Rope Climbs", "tip_category": "recovery", "content": "Builds tremendous grip strength and forearm endurance. Develop foot lock technique for efficiency."},
                    {"exercise_name": "Kettlebell Swings", "tip_category": "form", "content": "Hip hinge movement, not squatting. Explosive hip extension generates power, not arm strength."},
                    {"exercise_name": "Wall Balls", "tip_category": "nutrition", "content": "High rep metabolic work requires adequate carb intake. Fuel before intense sessions."},
                    {"exercise_name": "Double Unders", "tip_category": "form", "content": "Jump slightly higher than regular rope, relax arms and use wrist speed for quick rotations."},
                ]
            },
            {
                "name": "Endurance Running Program",
                "description": "Build aerobic base and running endurance through structured training and progressive distance.",
                "category": "Cardio",
                "difficulty_level": "Intermediate",
                "duration_weeks": 12,
                "target_goals": "Endurance, Fat Loss, Cardiovascular Health",
                "equipment_needed": "Running Shoes, Hydration Pack",
                "tips": [
                    {"exercise_name": "Tempo Runs", "tip_category": "form", "content": "Run at 'comfortably hard' pace for 20-40 minutes. This builds lactate threshold."},
                    {"exercise_name": "Long Runs", "tip_category": "nutrition", "content": "For runs over 90 minutes, take gels or sports drinks. Practice fueling strategy during training."},
                    {"exercise_name": "Speed Work", "tip_category": "recovery", "content": "Include 1-2 speed sessions per week, but not consecutive days. Easy runs between hard efforts."},
                    {"exercise_name": "Hill Training", "tip_category": "form", "content": "Lean slightly forward, maintain cadence, drive knees up. Hills build strength and power."},
                    {"exercise_name": "Recovery Runs", "tip_category": "mental", "content": "Easy, conversational pace runs aid recovery and build aerobic base. Don't race every run."},
                ]
            },
            {
                "name": "Core Stability Intensive",
                "description": "Targeted core strengthening for injury prevention, better performance, and improved posture.",
                "category": "Strength",
                "difficulty_level": "Intermediate",
                "duration_weeks": 5,
                "target_goals": "Core Strength, Stability, Posture, Injury Prevention",
                "equipment_needed": "Stability Ball, Resistance Bands, Ab Wheel",
                "tips": [
                    {"exercise_name": "Planks", "tip_category": "form", "content": "Straight line from head to heels, engage glutes and abs. Avoid sagging hips or piking."},
                    {"exercise_name": "Dead Bugs", "tip_category": "recovery", "content": "Controlled movement protects lower back. Move opposite arm and leg slowly and deliberately."},
                    {"exercise_name": "Pallof Press", "tip_category": "mental", "content": "Anti-rotation exercise teaches core engagement. Focus on not rotating through spine."},
                    {"exercise_name": "Ab Wheel Rollouts", "tip_category": "form", "content": "Start on knees, control the descent, use core to pull back up. Advanced progression: standing rollouts."},
                    {"exercise_name": "Bird Dogs", "tip_category": "recovery", "content": "Excellent for lower back health. Extend opposite limbs with steady breathing, no jerking."},
                ]
            },
            {
                "name": "Kettlebell Conditioning",
                "description": "Time-efficient full-body workout using kettlebell movements for strength, power, and conditioning.",
                "category": "Functional",
                "difficulty_level": "Intermediate",
                "duration_weeks": 6,
                "target_goals": "Muscular Endurance, Conditioning, Strength",
                "equipment_needed": "Kettlebells (Various Weights)",
                "tips": [
                    {"exercise_name": "Kettlebell Goblet Squats", "tip_category": "form", "content": "Hold kettlebell at chest, squat deep, keep torso upright. Great for teaching proper squat mechanics."},
                    {"exercise_name": "Turkish Get-ups", "tip_category": "form", "content": "Complex movement teaching full-body control. Go slow, focus on each transition. Excellent for shoulder stability."},
                    {"exercise_name": "Kettlebell Snatches", "tip_category": "recovery", "content": "Explosive hip power movement. Start light and focus on technique before increasing weight."},
                    {"exercise_name": "Farmer's Carries", "tip_category": "mental", "content": "Walk with heavy kettlebells. Builds grip strength and core endurance for functional fitness."},
                    {"exercise_name": "Renegade Rows", "tip_category": "form", "content": "From plank position with hands on kettlebells, row one up while stabilizing with other side."},
                ]
            },
            {
                "name": "Pilates for Strength",
                "description": "Low-impact but intense Pilates routine building lean muscle, flexibility, and mind-body connection.",
                "category": "Flexibility",
                "difficulty_level": "Intermediate",
                "duration_weeks": 4,
                "target_goals": "Lean Muscle, Flexibility, Core Strength",
                "equipment_needed": "Pilates Mat, Resistance Ring, Foam Roller",
                "tips": [
                    {"exercise_name": "Hundred", "tip_category": "form", "content": "Pulse arms while maintaining ab engagement. Breathe continuously - 5 counts in, 5 counts out."},
                    {"exercise_name": "Single Leg Circle", "tip_category": "recovery", "content": "Controlled movement improves hip mobility. Keep pelvis square and stable throughout."},
                    {"exercise_name": "Rolling Bridge", "tip_category": "form", "content": "Articulate through spine one vertebra at a time. Glute work while mobilizing the spine."},
                    {"exercise_name": "Side-Lying Leg Series", "tip_category": "mental", "content": "Builds hip and glute endurance. Focus on control and small, precise movements."},
                    {"exercise_name": "Swan Dive", "tip_category": "recovery", "content": "Back extension movement counteracting daily flexion. Opens chest and strengthens posterior chain."},
                ]
            },
            {
                "name": "Advanced Fat Loss Circuit",
                "description": "Sport-specific and metabolic circuit training for rapid fat loss and athletic development.",
                "category": "Cardio",
                "difficulty_level": "Advanced",
                "duration_weeks": 6,
                "target_goals": "Fat Loss, Athletic Performance, Conditioning",
                "equipment_needed": "Dumbbells, Kettlebells, Rope, Medicine Ball, Battle Ropes",
                "tips": [
                    {"exercise_name": "Battle Ropes", "tip_category": "form", "content": "Alternate arms in rapid alternating waves. Keep core tight, shoulders back, generate power from core."},
                    {"exercise_name": "Medicine Ball Slams", "tip_category": "recovery", "content": "Explosive movement releasing tension. Singles or double arm - go with intensity."},
                    {"exercise_name": "Sled Pushes", "tip_category": "mental", "content": "Relentless metabolic tool. Lean into it, drive through legs, maintain steady breathing."},
                    {"exercise_name": "Prowler Sprints", "tip_category": "form", "content": "Short, explosive efforts. Walk back after each sprint for active recovery."},
                    {"exercise_name": "Farmer Walks on Incline", "tip_category": "nutrition", "content": "Heavy loaded carries on incline maximize calorie burn. Post-workout nutrition is essential for recovery."},
                ]
            },
            {
                "name": "Olympic Weightlifting Basics",
                "description": "Foundation building in the two Olympic lifts - snatch and clean & jerk - for strength and explosiveness.",
                "category": "Strength",
                "difficulty_level": "Advanced",
                "duration_weeks": 8,
                "target_goals": "Strength, Power, Athletic Performance",
                "equipment_needed": "Olympic Barbell, Weight Plates, Weight Bumpers, Lifting Platform",
                "tips": [
                    {"exercise_name": "Snatch", "tip_category": "form", "content": "Three phases: pull, transition, catch. Explosive hip extension is the power source. Speed under bar is critical."},
                    {"exercise_name": "Clean", "tip_category": "form", "content": "Explosive pull with aggressive hip extension and descent. Catch in quarter squat position, recover to standing."},
                    {"exercise_name": "Jerk", "tip_category": "recovery", "content": "Dip with vertical torso, explosive extension. Press in split or power position. Takes practice."},
                    {"exercise_name": "Power Cleans", "tip_category": "mental", "content": "Catch above parallel squat. Trains the pull and catch without needing extreme flexibility."},
                    {"exercise_name": "Muscle Snatches", "tip_category": "form", "content": "No leg bend in catch. Pure pulling and speed. Excellent for teaching proper bar path and timing."},
                ]
            },
        ]

        created_count = 0
        with transaction.atomic():
            for guide_data in guides_data:
                tips_data = guide_data.pop("tips")

                cat_lower = guide_data["category"].lower()
                if 'strength' in cat_lower:
                    img_name = 'guide_images/strength.jpg'
                elif 'cardio' in cat_lower:
                    img_name = 'guide_images/cardio.jpg'
                elif 'flexibility' in cat_lower or 'yoga' in cat_lower or 'pilates' in cat_lower or 'wellness' in cat_lower:
                    img_name = 'guide_images/yoga.jpg'
                elif 'hybrid' in cat_lower or 'crossfit' in cat_lower or 'functional' in cat_lower:
                    img_name = 'guide_images/hybrid.jpg'
                elif 'core' in cat_lower:
                    img_name = 'guide_images/core.jpg'
                else:
                    img_name = 'guide_images/strength.jpg'

                # Create or update guide
                guide, created = WorkoutGuide.objects.get_or_create(
                    name=guide_data["name"],
                    trainer=trainer,
                    defaults={
                        **guide_data,
                        "image": img_name,
                        "status": WorkoutGuide.Status.APPROVED,  # Auto-approve for demo
                    }
                )

                if created:
                    created_count += 1

                # Create tips
                for tip_data in tips_data:
                    WorkoutTip.objects.get_or_create(
                        guide=guide,
                        exercise_name=tip_data["exercise_name"],
                        tip_category=tip_data["tip_category"],
                        defaults={"content": tip_data["content"]}
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_count} new guides with {len(guides_data)} total guides in library"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"All guides are APPROVED and ready for members to browse and trainers to assign"
            )
        )
