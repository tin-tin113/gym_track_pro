import os, sys, django
from django.utils import timezone
import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gymtrack_django.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

u, created = User.objects.get_or_create(username='testmember', defaults={'email': 'testmember@example.com', 'role': 'member', 'full_name': 'Test Member'})
if created:
    u.set_password('Testpass123')
    u.save()
else:
    u.set_password('Testpass123')
    u.role = 'member'
    u.full_name = 'Test Member'
    u.save()

from tracker.models import Member
m, mc = Member.objects.get_or_create(
    user=u,
    defaults={
        'membership_start_date': timezone.localdate(),
        'membership_expiry_date': timezone.localdate() + datetime.timedelta(days=365),
        'is_approved': False,
    },
)
print('user', u.username, 'created', created, 'member_created', mc, 'is_approved', m.is_approved)

from django.test import Client
c = Client()
logged = c.login(username='testmember', password='Testpass123')
print('logged', logged)
resp = c.get('/member/guides/library', HTTP_HOST='127.0.0.1:8000')
print('status', resp.status_code)
print(resp.content.decode()[:1600])
