from django import forms
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.utils.html import format_html, mark_safe
from django.db import transaction
from .models import (
    Student, Course, Attendance, Profile, ClassGroup,
    QRSession, QRScan, Teacher, AdminProfile,
)


# ─────────────────────────────────────────────────────────────────────────────
# Inline: Profile role shown inside User change page
# ─────────────────────────────────────────────────────────────────────────────

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name = 'Role & Contact'
    fields = ('role', 'phone', 'address')
    extra = 0


class TeacherInline(admin.StackedInline):
    model = Teacher
    can_delete = False
    verbose_name = 'Teacher Details'
    fields = ('employee_id', 'department', 'specialization', 'date_hired')
    extra = 0


class AdminProfileInline(admin.StackedInline):
    model = AdminProfile
    can_delete = False
    verbose_name = 'Admin Details'
    fields = ('employee_id', 'department')
    extra = 0


# ─────────────────────────────────────────────────────────────────────────────
# Proxy models for role-filtered User views
# ─────────────────────────────────────────────────────────────────────────────

class AdminUser(User):
    class Meta:
        proxy = True
        verbose_name = '🛡 Admin'
        verbose_name_plural = '🛡 Admins'
        app_label = 'auth'


class TeacherUser(User):
    class Meta:
        proxy = True
        verbose_name = '👤 Teacher'
        verbose_name_plural = '👤 Teachers'
        app_label = 'auth'


class StudentUser(User):
    class Meta:
        proxy = True
        verbose_name = '🎓 Student'
        verbose_name_plural = '🎓 Students'
        app_label = 'auth'


# ─────────────────────────────────────────────────────────────────────────────
# Creation forms with role-specific extra fields
# ─────────────────────────────────────────────────────────────────────────────

class TeacherCreationForm(UserCreationForm):
    employee_id    = forms.CharField(max_length=20, required=False, label='Employee ID')
    department     = forms.CharField(max_length=100, required=False)
    specialization = forms.CharField(max_length=100, required=False)
    date_hired     = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    phone          = forms.CharField(max_length=20, required=False)
    address        = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')


class StudentCreationForm(UserCreationForm):
    student_id     = forms.CharField(max_length=20, required=False, label='Student ID')
    s_first_name   = forms.CharField(max_length=50, required=True, label='First Name')
    s_last_name    = forms.CharField(max_length=50, required=True, label='Last Name')
    section        = forms.CharField(max_length=50, required=False)
    department     = forms.CharField(max_length=100, required=False)
    parent_contact = forms.CharField(max_length=20, required=False)
    class_group    = forms.ModelChoiceField(queryset=ClassGroup.objects.all(), required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')


# ─────────────────────────────────────────────────────────────────────────────
# Base role admin
# ─────────────────────────────────────────────────────────────────────────────

class RoleFilteredUserAdmin(UserAdmin):
    list_display       = ('id', 'username', 'first_name', 'last_name', 'email', 'is_active')
    list_display_links = ('id', 'username')
    ordering           = ('id',)
    role_filter        = None

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.role_filter:
            qs = qs.filter(profile__role=self.role_filter)
        return qs

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if self.role_filter:
            Profile.objects.update_or_create(user=obj, defaults={'role': self.role_filter})


# ── Teacher admin in Django panel ─────────────────────────────────────────────

@admin.register(TeacherUser)
class TeacherUserAdmin(RoleFilteredUserAdmin):
    role_filter  = 'teacher'
    add_form     = TeacherCreationForm
    inlines      = [ProfileInline, TeacherInline]

    add_fieldsets = (
        ('Login Credentials', {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'email', 'password1', 'password2'),
        }),
        ('Teacher Details', {
            'fields': ('employee_id', 'department', 'specialization', 'date_hired', 'phone', 'address'),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Ensure Profile has teacher role
        profile, _ = Profile.objects.update_or_create(
            user=obj,
            defaults={
                'role': 'teacher',
                'phone': form.cleaned_data.get('phone', ''),
                'address': form.cleaned_data.get('address', ''),
            }
        )
        # Ensure Teacher record exists with extra details
        Teacher.objects.update_or_create(
            user=obj,
            defaults={
                'employee_id':    form.cleaned_data.get('employee_id') or None,
                'department':     form.cleaned_data.get('department', ''),
                'specialization': form.cleaned_data.get('specialization', ''),
                'date_hired':     form.cleaned_data.get('date_hired'),
            }
        )


# ── Student admin in Django panel ─────────────────────────────────────────────

@admin.register(StudentUser)
class StudentUserAdmin(RoleFilteredUserAdmin):
    role_filter  = 'student'
    add_form     = StudentCreationForm
    inlines      = [ProfileInline]

    # Show Student model fields instead of User fields
    list_display       = ('student_id_display', 'student_full_name', 'username', 'student_class', 'email', 'is_active')
    list_display_links = ('student_id_display', 'username')
    ordering           = ('id',)

    def student_id_display(self, obj):
        try:
            return obj.student_profile.student_id or f'#{obj.id}'
        except Exception:
            return f'#{obj.id}'
    student_id_display.short_description = 'Student ID'

    def student_full_name(self, obj):
        try:
            s = obj.student_profile
            return f'{s.first_name} {s.last_name}'
        except Exception:
            return obj.get_full_name() or obj.username
    student_full_name.short_description = 'Full Name'

    def student_class(self, obj):
        try:
            cg = obj.student_profile.class_group
            return str(cg) if cg else '—'
        except Exception:
            return '—'
    student_class.short_description = 'Class'

    add_fieldsets = (
        ('Login Credentials', {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
        ('Student Details', {
            'fields': ('s_first_name', 's_last_name', 'student_id', 'section', 'department', 'parent_contact', 'class_group'),
        }),
    )

    def save_model(self, request, obj, form, change):
        # Set first/last name from student fields on new users
        if not change:
            obj.first_name = form.cleaned_data.get('s_first_name', '')
            obj.last_name  = form.cleaned_data.get('s_last_name', '')
        super().save_model(request, obj, form, change)
        # Ensure Profile has student role
        Profile.objects.update_or_create(user=obj, defaults={'role': 'student'})
        # Create or update Student record
        if not change:
            Student.objects.update_or_create(
                user=obj,
                defaults={
                    'student_id':     form.cleaned_data.get('student_id') or None,
                    'first_name':     form.cleaned_data.get('s_first_name', ''),
                    'last_name':      form.cleaned_data.get('s_last_name', ''),
                    'section':        form.cleaned_data.get('section', ''),
                    'department':     form.cleaned_data.get('department', ''),
                    'parent_contact': form.cleaned_data.get('parent_contact', ''),
                    'class_group':    form.cleaned_data.get('class_group'),
                }
            )


# ── Admin user in Django panel ────────────────────────────────────────────────

@admin.register(AdminUser)
class AdminUserAdmin(RoleFilteredUserAdmin):
    role_filter = 'admin'
    inlines     = [ProfileInline, AdminProfileInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        Profile.objects.update_or_create(user=obj, defaults={'role': 'admin'})
        AdminProfile.objects.get_or_create(user=obj)


# ─────────────────────────────────────────────────────────────────────────────
# Main Users list (all roles, with badge)
# ─────────────────────────────────────────────────────────────────────────────

class CustomUserAdmin(UserAdmin):
    list_display       = ('id', 'username', 'first_name', 'last_name', 'email', 'role_badge', 'is_staff')
    list_display_links = ('id', 'username')
    list_filter        = ('profile__role', 'is_staff', 'is_active')
    ordering           = ('id',)
    inlines            = [ProfileInline]

    def role_badge(self, obj):
        try:
            role = obj.profile.role
        except Exception:
            return format_html('<span style="color:#94a3b8;">—</span>')
        colors = {
            'admin':   ('#3b82f6', '🛡 Admin'),
            'teacher': ('#8b5cf6', '👤 Teacher'),
            'student': ('#10b981', '🎓 Student'),
        }
        color, label = colors.get(role, ('#94a3b8', role))
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:12px;font-size:12px;font-weight:700;">{}</span>',
            color, label
        )
    role_badge.short_description = 'Role'


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


# ─────────────────────────────────────────────────────────────────────────────
# Student
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display       = ('id', 'first_name', 'last_name', 'student_id', 'class_group', 'get_courses', 'has_login')
    list_display_links = ('id', 'first_name')
    search_fields      = ('first_name', 'last_name', 'student_id')
    list_filter        = ('class_group',)
    filter_horizontal  = ('courses',)
    ordering           = ('id',)

    def get_courses(self, obj):
        return ', '.join([c.course_name for c in obj.courses.all()]) or '—'
    get_courses.short_description = 'Courses'

    def has_login(self, obj):
        if obj.user:
            return mark_safe('<span style="color:#22c55e;font-weight:700;">✔ Yes</span>')
        return mark_safe('<span style="color:#ef4444;">✘ No</span>')
    has_login.short_description = 'Login Account'


# ─────────────────────────────────────────────────────────────────────────────
# Course
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display       = ('id', 'course_name', 'teacher')
    list_display_links = ('id', 'course_name')
    search_fields      = ('course_name',)
    ordering           = ('id',)


# ─────────────────────────────────────────────────────────────────────────────
# Attendance
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display  = ('id', 'student', 'course', 'date', 'colored_status', 'remarks')
    list_filter   = ('status', 'course', 'date')
    search_fields = ('student__first_name', 'student__last_name')
    ordering      = ('-date',)

    def colored_status(self, obj):
        colors = {'Present': '#22c55e', 'Absent': '#ef4444', 'Late': '#f59e0b'}
        color = colors.get(obj.status, '#94a3b8')
        return format_html('<span style="color:{};font-weight:700;">{}</span>', color, obj.status)
    colored_status.short_description = 'Status'


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'role_badge', 'phone')
    list_filter   = ('role',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

    def role_badge(self, obj):
        colors = {
            'admin':   ('#3b82f6', '🛡 Admin'),
            'teacher': ('#8b5cf6', '👤 Teacher'),
            'student': ('#10b981', '🎓 Student'),
        }
        color, label = colors.get(obj.role, ('#94a3b8', obj.role))
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:12px;font-size:12px;font-weight:700;">{}</span>',
            color, label
        )
    role_badge.short_description = 'Role'


# ─────────────────────────────────────────────────────────────────────────────
# ClassGroup
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display  = ('id', 'name', 'section', 'adviser')
    search_fields = ('name',)
    ordering      = ('name', 'section')


# ─────────────────────────────────────────────────────────────────────────────
# Teacher
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'employee_id', 'department', 'specialization', 'date_hired')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'employee_id')
    list_filter   = ('department',)
    ordering      = ('user__last_name',)


# ─────────────────────────────────────────────────────────────────────────────
# AdminProfile
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'employee_id', 'department')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'employee_id')
    ordering      = ('user__last_name',)


# ─────────────────────────────────────────────────────────────────────────────
# QRSession
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(QRSession)
class QRSessionAdmin(admin.ModelAdmin):
    list_display  = ('session_id', 'created_by', 'date', 'expires_at', 'is_active', 'scan_count')
    list_filter   = ('is_active', 'date')
    ordering      = ('-created_at',)

    def scan_count(self, obj):
        return obj.scans.count()
    scan_count.short_description = 'Scans'


# ─────────────────────────────────────────────────────────────────────────────
# Admin site branding
# ─────────────────────────────────────────────────────────────────────────────

admin.site.site_header = 'SAMS Administration'
admin.site.site_title  = 'SAMS Admin'
admin.site.index_title = 'School Attendance Management'
