from django.core.management.base import BaseCommand
from django.utils import timezone
from tracker.models import WorkoutGuide, WorkoutTip


class Command(BaseCommand):
	help = 'Seed the database with 10+ approved workout guides with realistic tips'

	def handle(self, *args, **options):
		# Guides data with tips
		guides_data = [
			{
				'name': 'Beginner Full Body Strength',
				'category': 'Strength Training',
				'difficulty_level': 'Beginner',
				'description': 'Complete full-body workout for beginners focusing on compound movements and building a foundation for fitness. Perfect for starting your fitness journey with proper form and technique.',
				'duration_weeks': 4,
				'target_goals': 'Build muscle mass, Improve strength, Increase endurance',
				'equipment_needed': 'Dumbbells, Barbell, Bench',
				'tips': [
					{'exercise_name': 'Squats', 'tip_category': 'Form', 'content': 'Keep chest up, knees aligned with toes, and descend until thighs are parallel to ground.'},
					{'exercise_name': 'Squats', 'tip_category': 'Safety', 'content': 'Always warm up for 5-10 minutes before doing heavy squats.'},
					{'exercise_name': 'Bench Press', 'tip_category': 'Technique', 'content': 'Lower the bar to your chest, elbows at 45 degrees from body, then push explosively.'},
					{'exercise_name': 'Bench Press', 'tip_category': 'Progression', 'content': 'Start with an empty barbell, add weight gradually as you master the form.'},
					{'exercise_name': 'Deadlifts', 'tip_category': 'Form', 'content': 'Keep barbell close to your body, neutral spine, and drive through your heels.'},
				]
			},
			{
				'name': 'Intermediate Push/Pull Split',
				'category': 'Strength Training',
				'difficulty_level': 'Intermediate',
				'description': 'Advanced split routine separating push and pull movements for optimal muscle development and recovery. Ideal for those with 6+ months training experience.',
				'duration_weeks': 6,
				'target_goals': 'Muscle hypertrophy, Strength gains, Muscle definition',
				'equipment_needed': 'Full gym equipment',
				'tips': [
					{'exercise_name': 'Pull-ups', 'tip_category': 'Form', 'content': 'Full range of motion from dead hang to chin above bar, controlled descent.'},
					{'exercise_name': 'Pull-ups', 'tip_category': 'Scaling', 'content': 'Use resistance bands or assisted machine if you cannot do 8+ reps.'},
					{'exercise_name': 'Overhead Press', 'tip_category': 'Technique', 'content': 'Press from shoulder height, keep core tight, avoid arching lower back.'},
					{'exercise_name': 'Barbell Rows', 'tip_category': 'Form', 'content': 'Row to chest, squeeze shoulder blades, maintain neutral spine throughout.'},
					{'exercise_name': 'Dips', 'tip_category': 'Progression', 'content': 'Start with assisted dips or elevated position, progress to bodyweight.'},
				]
			},
			{
				'name': 'HIIT Cardio Blast',
				'category': 'Cardio',
				'difficulty_level': 'Intermediate',
				'description': 'High-intensity interval training to maximize fat loss in minimal time. 30-minute sessions combining sprints, jumping movements, and active recovery.',
				'duration_weeks': 4,
				'target_goals': 'Fat loss, Cardiovascular fitness, Endurance',
				'equipment_needed': 'Minimal - dumbbells optional',
				'tips': [
					{'exercise_name': 'Burpees', 'tip_category': 'Form', 'content': 'Landing softly, jump smoothly, and maintain explosive power throughout sets.'},
					{'exercise_name': 'Mountain Climbers', 'tip_category': 'Pacing', 'content': 'Maintain steady tempo for 40 seconds, keep core engaged throughout.'},
					{'exercise_name': 'Jump Rope', 'tip_category': 'Technique', 'content': 'Small hops on balls of feet, arms relaxed, consistent wrist rotation.'},
					{'exercise_name': 'Sprints', 'tip_category': 'Safety', 'content': 'Always warm up with 5 min light jogging before sprinting.'},
					{'exercise_name': 'Rest Periods', 'tip_category': 'Recovery', 'content': 'Active recovery: light walking or slow movement for 30-45 seconds.'},
				]
			},
			{
				'name': 'Mind-Body Yoga Flow',
				'category': 'Flexibility/Wellness',
				'difficulty_level': 'Beginner',
				'description': 'Gentle yoga practice combining mindfulness, breathing techniques, and flowing poses. Improve flexibility, reduce stress, and enhance mind-body connection.',
				'duration_weeks': 8,
				'target_goals': 'Flexibility, Stress relief, Mind-body alignment',
				'equipment_needed': 'Yoga mat, Block',
				'tips': [
					{'exercise_name': 'Downward Dog', 'tip_category': 'Alignment', 'content': 'Spread fingers wide, press firmly, shoulders over wrists, body in inverted V.'},
					{'exercise_name': 'Warrior Pose', 'tip_category': 'Balance', 'content': 'Front knee over ankle, back foot at 45 degrees, arms extended.'},
					{'exercise_name': 'Breathing', 'tip_category': 'Technique', 'content': 'Use Ujjayi breathing: deep, controlled breaths through nose throughout practice.'},
					{'exercise_name': 'Child Pose', 'tip_category': 'Rest', 'content': 'Use as restorative break between flows, focus on deep breathing.'},
					{'exercise_name': 'Meditation', 'tip_category': 'Mindfulness', 'content': 'Spend 5-10 minutes in silence at end of session focusing on breathing.'},
				]
			},
			{
				'name': 'CrossFit Fundamentals',
				'category': 'Hybrid Training',
				'difficulty_level': 'Advanced',
				'description': 'Functional fitness combining weightlifting, gymnastics, and high-intensity metabolic conditioning. Requires proficiency in basic movements.',
				'duration_weeks': 6,
				'target_goals': 'Functional strength, Explosive power, Conditioning',
				'equipment_needed': 'Barbell, Kettlebells, Rings, Pull-up bar',
				'tips': [
					{'exercise_name': 'Kipping Pull-ups', 'tip_category': 'Technique', 'content': 'Use hip drive to generate momentum, timing is critical for efficiency.'},
					{'exercise_name': 'Box Jumps', 'tip_category': 'Form', 'content': 'Soft landing on box, controlled descent, explosive takeoff.'},
					{'exercise_name': 'Kettlebell Swings', 'tip_category': 'Movement', 'content': 'Hip hinge movement, not squat, explosive hip extension drives bell.'},
					{'exercise_name': 'Rope Climbs', 'tip_category': 'Progression', 'content': 'Master the motion first with feet on ground, progress to full climbs.'},
					{'exercise_name': 'Olympic Lifts', 'tip_category': 'Safety', 'content': 'Get professional coaching before attempting max efforts on snatches/cleans.'},
				]
			},
			{
				'name': 'Endurance Running Program',
				'category': 'Cardio',
				'difficulty_level': 'Intermediate',
				'description': 'Structured 12-week program building running endurance from 5K to half-marathon distances. Combines tempo runs, long runs, and easy recovery days.',
				'duration_weeks': 12,
				'target_goals': 'Endurance, Speed, Running efficiency',
				'equipment_needed': 'Running shoes, Hydration pack',
				'tips': [
					{'exercise_name': 'Long Run', 'tip_category': 'Pacing', 'content': 'Run at conversational pace, should be able to speak in sentences.'},
					{'exercise_name': 'Tempo Run', 'tip_category': 'Intensity', 'content': 'Warm up 10 min, run 20-40 min at challenging but sustainable pace.'},
					{'exercise_name': 'Recovery Run', 'tip_category': 'Technique', 'content': 'Easy pace day after hard efforts, promotes blood flow and adaptation.'},
					{'exercise_name': 'Breathing', 'tip_category': 'Form', 'content': 'Rhythmic breathing reduces oxygen depletion mid-workout.'},
					{'exercise_name': 'Hydration', 'tip_category': 'Fueling', 'content': 'Drink 8oz water every 20 minutes on long runs over 60 minutes.'},
				]
			},
			{
				'name': 'Core Stability Intensive',
				'category': 'Strength Training',
				'difficulty_level': 'Intermediate',
				'description': 'Targeted program focusing on core muscles to improve posture, prevent injury, and enhance athletic performance. Includes planks, rotations, and anti-rotation work.',
				'duration_weeks': 8,
				'target_goals': 'Core strength, Injury prevention, Posture',
				'equipment_needed': 'Mat, Stability ball, Ab wheel',
				'tips': [
					{'exercise_name': 'Plank', 'tip_category': 'Form', 'content': 'Shoulders over wrists, neutral spine, glutes engaged, avoid sagging hips.'},
					{'exercise_name': 'Dead Bug', 'tip_category': 'Technique', 'content': 'Opposite arm-leg extends simultaneously while maintaining neutral spine.'},
					{'exercise_name': 'Ab Wheel', 'tip_category': 'Progression', 'content': 'Start from knees, progress to full body extension as strength increases.'},
					{'exercise_name': 'Pallof Press', 'tip_category': 'Movement', 'content': 'Anti-rotation exercise, resist twisting with core muscles.'},
					{'exercise_name': 'Breathing', 'tip_category': 'Technique', 'content': 'Never hold breath during core work, maintain steady breathing pattern.'},
				]
			},
			{
				'name': 'Kettlebell Conditioning',
				'category': 'Strength Training',
				'difficulty_level': 'Intermediate',
				'description': 'Full-body conditioning program using kettlebells to build functional strength and cardiovascular fitness. Combines swings, snatches, and carries.',
				'duration_weeks': 6,
				'target_goals': 'Muscular endurance, Fat loss, Functional strength',
				'equipment_needed': 'Kettlebells (16kg, 24kg)',
				'tips': [
					{'exercise_name': 'Kettlebell Swing', 'tip_category': 'Mechanics', 'content': 'Hip hinge not squat, explosive hip drive, arm path follows body momentum.'},
					{'exercise_name': 'Kettlebell Snatch', 'tip_category': 'Form', 'content': 'Explosive pull-up with hip drive, guide bell to top position, catch firmly.'},
					{'exercise_name': 'Farmer Carry', 'tip_category': 'Posture', 'content': 'Heavy load, neutral spine, chest up, walk purposefully avoiding lean.'},
					{'exercise_name': 'Turkish Getup', 'tip_category': 'Complexity', 'content': 'Highly technical, master each position slowly before linking movements.'},
					{'exercise_name': 'Recovery', 'tip_category': 'Volume', 'content': 'Kettlebell training is intense, prioritize sleep and nutrition.'},
				]
			},
			{
				'name': 'Pilates for Strength',
				'category': 'Flexibility/Wellness',
				'difficulty_level': 'Intermediate',
				'description': 'Pilates-based strength training emphasizing precision, control, and core stability. Low-impact but highly effective for muscle tone and injury prevention.',
				'duration_weeks': 8,
				'target_goals': 'Muscular endurance, Core strength, Flexibility',
				'equipment_needed': 'Mat, Pillow, Resistance band',
				'tips': [
					{'exercise_name': 'Reformer Work', 'tip_category': 'Equipment', 'content': 'Use springs for resistance, adjust tension for appropriate challenge level.'},
					{'exercise_name': 'Core Engagement', 'tip_category': 'Technique', 'content': 'Draw navel in and up throughout all movements for proper engagement.'},
					{'exercise_name': 'Breathing', 'tip_category': 'Method', 'content': 'Inhale during preparation, exhale during exertion for max power.'},
					{'exercise_name': 'Precision', 'tip_category': 'Form', 'content': 'Quality over quantity, fewer reps with perfect form is superior.'},
					{'exercise_name': 'Flexibility Focus', 'tip_category': 'Benefit', 'content': 'Pilates maintains length in muscles while building strength.'},
				]
			},
			{
				'name': 'Advanced Fat Loss Circuit',
				'category': 'Hybrid Training',
				'difficulty_level': 'Advanced',
				'description': 'High-intensity circuit combining strength and cardio for maximum fat loss and metabolic conditioning. 3 days/week of strategic training.',
				'duration_weeks': 8,
				'target_goals': 'Fat loss, Muscle preservation, Cardiovascular conditioning',
				'equipment_needed': 'Full gym equipment',
				'tips': [
					{'exercise_name': 'Circuit Design', 'tip_category': 'Planning', 'content': 'Alternate muscle groups to maintain intensity while allowing partial recovery.'},
					{'exercise_name': 'Density Training', 'tip_category': 'Method', 'content': 'Complete set workout in shorter time as weeks progress, track time carefully.'},
					{'exercise_name': 'Nutrition', 'tip_category': 'Support', 'content': 'Maintain caloric deficit of 300-500 calories for optimal fat loss results.'},
					{'exercise_name': 'Recovery', 'tip_category': 'Protocol', 'content': '90-120 seconds between circuits, active recovery on off days.'},
					{'exercise_name': 'Progressive Overload', 'tip_category': 'Progression', 'content': 'Add 1-2 reps or reduce rest time weekly to continue adaptation.'},
				]
			},
			{
				'name': 'Olympic Weightlifting Basics',
				'category': 'Strength Training',
				'difficulty_level': 'Advanced',
				'description': 'Technical introduction to snatch and clean & jerk movements. Focuses on proper form, mobility, and foundational strength before max efforts.',
				'duration_weeks': 6,
				'target_goals': 'Explosive power, Technical skill, Strength',
				'equipment_needed': 'Olympic barbell, Bumper plates, Platform',
				'tips': [
					{'exercise_name': 'Snatch', 'tip_category': 'Technique', 'content': 'Master position sequencing: setup, pull, transition, catch, recovery.'},
					{'exercise_name': 'Clean & Jerk', 'tip_category': 'Skill', 'content': 'Two-part lift, clean to shoulders, then jerk overhead with dip and drive.'},
					{'exercise_name': 'Mobility', 'tip_category': 'Prerequisite', 'content': 'Requires shoulder, hip, and ankle mobility before attempting heavy loads.'},
					{'exercise_name': 'Coaching', 'tip_category': 'Safety', 'content': 'Professional coaching is essential - improper form leads to serious injury.'},
					{'exercise_name': 'Bottom Position', 'tip_category': 'Power', 'content': 'Practice receiving position regularly to build comfort and stability.'},
				]
			},
		]

		# Create guides
		admin_user = None
		try:
			from tracker.models import User
			admin_user = User.objects.filter(role='admin').first()
		except Exception:
			pass

		created_count = 0
		skipped_count = 0

		for guide_data in guides_data:
			# Check if guide already exists
			if WorkoutGuide.objects.filter(name=guide_data['name']).exists():
				self.stdout.write(
					self.style.WARNING(f'SKIP: "{guide_data["name"]}" - already exists')
				)
				skipped_count += 1
				continue

			try:
				# Create guide
				guide = WorkoutGuide.objects.create(
					name=guide_data['name'],
					description=guide_data['description'],
					category=guide_data['category'],
					difficulty_level=guide_data['difficulty_level'],
					duration_weeks=guide_data['duration_weeks'],
					target_goals=guide_data['target_goals'],
					equipment_needed=guide_data['equipment_needed'],
					status=WorkoutGuide.Status.APPROVED,
					trainer=admin_user,
					created_at=timezone.now(),
					updated_at=timezone.now(),
				)

				# Create tips
				tip_count = 0
				for order, tip_data in enumerate(guide_data['tips'], start=1):
					WorkoutTip.objects.create(
						guide=guide,
						exercise_name=tip_data['exercise_name'],
						tip_category=tip_data['tip_category'],
						content=tip_data['content'],
						order=order,
					)
					tip_count += 1

				self.stdout.write(
					self.style.SUCCESS(f'OK: Created "{guide.name}" with {tip_count} tips')
				)
				created_count += 1

			except Exception as e:
				self.stdout.write(
					self.style.ERROR(f'ERR: Error creating "{guide_data["name"]}": {str(e)}')
				)

		self.stdout.write(
			self.style.SUCCESS(
				f'\nSeed completed: {created_count} guides created, {skipped_count} skipped'
			)
		)
