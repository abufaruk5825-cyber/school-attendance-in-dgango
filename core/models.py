import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# ---------------------------------------------------------------------------
# Profile – extends Django's built-in User with a role (admin/teacher/student)
# ---------------------------------------------------------------------------

class Profile(models.Model):
    """
    One-to-one extension of Django's User model.
    Drives role-based access: every user (admin, teacher, student) has a Profile.
    """
    ROLE_CHOICES = [('admin', 'Admin'), ('teacher', 'Teacher'), ('student', 'Student')]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='teacher')
    phone = models.CharField(max_length=20, blank=True, default='')
    address = models.TextField(blank=True, default='')

    def __str__(self):
        return f"{self.user.username} ({self.role})"


# ---------------------------------------------------------------------------
# Teacher – dedicated table for teacher-specific data
# ---------------------------------------------------------------------------

class Teacher(models.Model):
    """
    Stores teacher-specific information.
    Linked 1-to-1 with a User whose Profile.role == 'teacher'.
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='teacher_profile'
    )
    employee_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True, default='')
    specialization = models.CharField(max_length=100, blank=True, default='')
    date_hired = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} (Teacher)"


# ---------------------------------------------------------------------------
# Admin – dedicated table for admin-specific data
# ---------------------------------------------------------------------------

class AdminProfile(models.Model):
    """
    Stores admin-specific information.
    Linked 1-to-1 with a User whose Profile.role == 'admin'.
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='admin_profile'
    )
    employee_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True, default='')

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} (Admin)"


# ---------------------------------------------------------------------------
# ClassGroup – a class/grade section (e.g. Grade 10-A)
# ---------------------------------------------------------------------------

class ClassGroup(models.Model):
    """Represents a class/grade (e.g. Grade 10, Class 9B)"""
    name = models.CharField(max_length=100)  # e.g. "Grade 10"
    section = models.CharField(max_length=5, blank=True, default='')  # A-E
    # Homeroom / adviser
    adviser = models.ForeignKey(
        Teacher, on_delete=models.SET_NULL, null=True, blank=True, related_name='advised_classes'
    )

    class Meta:
        ordering = ['name', 'section']
        unique_together = ('name', 'section')

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Course – unified course/subject model
# ---------------------------------------------------------------------------

class Course(models.Model):
    """
    A course or subject taught by a teacher, optionally linked to a class group.
    Replaces the old separate Subject model — class_group is the extra field merged in.
    """
    course_name = models.CharField(max_length=100)
    teacher = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        limit_choices_to={'profile__role': 'teacher'}
    )
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='courses'
    )

    def __str__(self):
        return self.course_name


# ---------------------------------------------------------------------------
# Student – dedicated table for student-specific data
# ---------------------------------------------------------------------------

class Student(models.Model):
    """
    Stores student-specific information.
    Linked 1-to-1 with a User whose Profile.role == 'student'.
    """
    student_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    section = models.CharField(max_length=50, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    parent_contact = models.CharField(max_length=20, null=True, blank=True)
    photo = models.ImageField(upload_to='students/photos/', null=True, blank=True)
    # Belongs to a class group
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='students'
    )
    # Keep old M2M for backward compat
    courses = models.ManyToManyField(Course, blank=True)
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='student_profile'
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


# ---------------------------------------------------------------------------
# Attendance – daily attendance record per student per course
# ---------------------------------------------------------------------------

class Attendance(models.Model):
    STATUS_CHOICES = [('Present', 'Present'), ('Absent', 'Absent'), ('Late', 'Late')]
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    remarks = models.CharField(max_length=100, blank=True, default='')
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_attendances'
    )
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_attendances'
    )

    class Meta:
        unique_together = ('student', 'course', 'date')

    def __str__(self):
        return f"{self.student} - {self.course} - {self.date} - {self.status}"


# ---------------------------------------------------------------------------
# QR Code Attendance System
# ---------------------------------------------------------------------------

class QRSession(models.Model):
    """A QR code attendance session generated by a teacher/admin."""
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True)
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def is_valid(self):
        return self.is_active and timezone.now() < self.expires_at

    def __str__(self):
        ref = self.course or self.class_group
        return f"QR Session {self.session_id} – {ref} – {self.date}"


class QRScan(models.Model):
    """Records each student's QR scan to prevent duplicates."""
    session = models.ForeignKey(QRSession, on_delete=models.CASCADE, related_name='scans')
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('session', 'student')

    def __str__(self):
        return f"{self.student} scanned {self.session.session_id}"
