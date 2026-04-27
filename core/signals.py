from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import Profile, Teacher, AdminProfile


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    """Auto-create a Profile for every new User."""
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=Profile)
def sync_role_records(sender, instance, **kwargs):
    """
    When a Profile's role is saved, ensure the matching role-specific
    record (Teacher / AdminProfile) exists.
    Student records are created explicitly in the view/admin.
    """
    if instance.role == 'teacher':
        Teacher.objects.get_or_create(user=instance.user)
    elif instance.role == 'admin':
        AdminProfile.objects.get_or_create(user=instance.user)
