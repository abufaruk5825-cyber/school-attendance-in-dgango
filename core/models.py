from django.db import models
from django.contrib.auth.models import User


class ClassGroup(models.Model):
    """Represents a class/grade (e.g. Grade 10, Class 9B)"""
    name = models.CharField(max_length=100)  # e.g. "Grade 10"
    section = models.CharField(max_length=5, blank=True, default='')  # A-E

    class Meta:
        ordering = ['name', 'section']
        unique_together = ('name', 'section')

    def __str__(self):
        if self.section:
            return f"{self.name} - Section {self.section}"
        return self.name


class Subject(models.Model):
    """A subject/course taught in a class by a teacher"""
    subject_name = models.CharField(max_length=100)
    class_group = models.ForeignKey(ClassGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='subjects')
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 limit_choices_to={'profile__role': 'teacher'})

    def __str__(self):
        if self.class_group:
            return f"{self.subject_name} ({self.class_group})"
        return self.subject_name


# Keep Course as alias for backward compatibility during transition
class Course(models.Model):
    course_name = models.CharField(max_length=100)
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 limit_choices_to={'profile__role': 'teacher'})

    def __str__(self):
        return self.course_name


class Student(models.Model):
    student_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    section = models.CharField(max_length=50, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    parent_contact = models.CharField(max_length=20, null=True, blank=True)
    # New: belongs to a class
    class_group = models.ForeignKey(ClassGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    # Keep old M2M for backward compat
    courses = models.ManyToManyField(Course, blank=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='student_profile')

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Attendance(models.Model):
    STATUS_CHOICES = [('Present', 'Present'), ('Absent', 'Absent'), ('Late', 'Late')]
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        unique_together = ('student', 'course', 'subject', 'date')

    def __str__(self):
        ref = self.subject or self.course
        return f"{self.student} - {ref} - {self.date} - {self.status}"


class Profile(models.Model):
    ROLE_CHOICES = [('admin', 'Admin'), ('teacher', 'Teacher'), ('student', 'Student')]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='teacher')

    def __str__(self):
        return f"{self.user.username} ({self.role})"
