"""
Run: python seed.py
Creates demo admin, teacher, courses, students, and sample attendance.
"""
import os
import django
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sams.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Profile, Course, Student, Attendance

# Admin
admin, _ = User.objects.get_or_create(username='admin')
admin.set_password('admin123')
admin.is_staff = True
admin.is_superuser = True
admin.save()
Profile.objects.update_or_create(user=admin, defaults={'role': 'admin'})

# Teacher
teacher, _ = User.objects.get_or_create(username='teacher1', defaults={'first_name': 'John', 'last_name': 'Smith'})
teacher.set_password('teacher123')
teacher.save()
Profile.objects.update_or_create(user=teacher, defaults={'role': 'teacher'})

# Teacher 2
teacher2, _ = User.objects.get_or_create(username='teacher2', defaults={'first_name': 'Sarah', 'last_name': 'Lee'})
teacher2.set_password('teacher123')
teacher2.save()
Profile.objects.update_or_create(user=teacher2, defaults={'role': 'teacher'})

# Courses (8)
c1, _ = Course.objects.get_or_create(course_name='Mathematics',       defaults={'teacher': teacher})
c2, _ = Course.objects.get_or_create(course_name='Science',           defaults={'teacher': teacher})
c3, _ = Course.objects.get_or_create(course_name='English',           defaults={'teacher': teacher})
c4, _ = Course.objects.get_or_create(course_name='History',           defaults={'teacher': teacher2})
c5, _ = Course.objects.get_or_create(course_name='Geography',         defaults={'teacher': teacher2})
c6, _ = Course.objects.get_or_create(course_name='Computer Science',  defaults={'teacher': teacher2})
c7, _ = Course.objects.get_or_create(course_name='Physics',           defaults={'teacher': teacher})
c8, _ = Course.objects.get_or_create(course_name='Chemistry',         defaults={'teacher': teacher2})

# Students (20)
students_data = [
    ('Alice',   'Johnson',  [c1]),      ('Bob',     'Williams', [c1]),      ('Carol',   'Brown',    [c1, c2]),
    ('David',   'Jones',    [c2]),      ('Eve',     'Davis',    [c2]),      ('Frank',   'Miller',   [c2, c3]),
    ('Grace',   'Wilson',   [c3]),      ('Henry',   'Moore',    [c3]),      ('Isla',    'Taylor',   [c3, c4]),
    ('Jack',    'Anderson', [c4]),      ('Karen',   'Thomas',   [c4]),      ('Liam',    'Jackson',  [c4, c5]),
    ('Mia',     'White',    [c5]),      ('Noah',    'Harris',   [c5]),      ('Olivia',  'Martin',   [c6]),
    ('Peter',   'Garcia',   [c6]),      ('Quinn',   'Martinez', [c7]),      ('Rachel',  'Robinson', [c7]),
    ('Samuel',  'Clark',    [c8]),      ('Tina',    'Rodriguez',[c8]),
]
students = []
for fn, ln, courses in students_data:
    s, _ = Student.objects.get_or_create(first_name=fn, last_name=ln)
    s.courses.set(courses)
    students.append(s)

# Sample attendance for last 7 days
import random
today = datetime.date.today()
for i in range(7):
    day = today - datetime.timedelta(days=i)
    for s in students:
        for course in s.courses.all():
            status = random.choice(['Present', 'Present', 'Present', 'Absent'])
            Attendance.objects.get_or_create(student=s, course=course, date=day, defaults={'status': status})

print("Seed complete!")
print("Admin login: admin / admin123")
print("Teacher login: teacher1 / teacher123")
