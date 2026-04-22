from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import Student, Course, Attendance, Profile, ClassGroup, Subject, QRSession, QRScan


# ── Proxy models for role-filtered User views ─────────────────────────────────
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


# ── Base role admin ───────────────────────────────────────────────────────────
class RoleFilteredUserAdmin(UserAdmin):
    list_display       = ('id', 'username', 'first_name', 'last_name', 'email', 'is_active')
    list_display_links = ('id', 'username')
    ordering           = ('id',)
    role_filter        = None   # override in subclass

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.role_filter:
            qs = qs.filter(profile__role=self.role_filter)
        return qs

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if self.role_filter:
            Profile.objects.update_or_create(user=obj, defaults={'role': self.role_filter})


@admin.register(AdminUser)
class AdminUserAdmin(RoleFilteredUserAdmin):
    role_filter = 'admin'

@admin.register(TeacherUser)
class TeacherUserAdmin(RoleFilteredUserAdmin):
    role_filter = 'teacher'

@admin.register(StudentUser)
class StudentUserAdmin(RoleFilteredUserAdmin):
    role_filter = 'student'


# ── Main Users list (all roles, with badge) ───────────────────────────────────
class CustomUserAdmin(UserAdmin):
    list_display       = ('id', 'username', 'first_name', 'last_name', 'email', 'role_badge', 'is_staff')
    list_display_links = ('id', 'username')
    list_filter        = ('profile__role', 'is_staff', 'is_active')
    ordering           = ('id',)

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


# ── Student ───────────────────────────────────────────────────────────────────
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
            return format_html('<span style="color:#22c55e;font-weight:700;">✔ Yes</span>')
        return format_html('<span style="color:#ef4444;">✘ No</span>')
    has_login.short_description = 'Login Account'


# ── Course ────────────────────────────────────────────────────────────────────
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display       = ('id', 'course_name', 'teacher')
    list_display_links = ('id', 'course_name')
    search_fields      = ('course_name',)
    ordering           = ('id',)


# ── Attendance ────────────────────────────────────────────────────────────────
@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display  = ('id', 'student', 'course', 'date', 'colored_status')
    list_filter   = ('status', 'course', 'date')
    search_fields = ('student__first_name', 'student__last_name')
    ordering      = ('-date',)

    def colored_status(self, obj):
        colors = {'Present': '#22c55e', 'Absent': '#ef4444', 'Late': '#f59e0b'}
        color = colors.get(obj.status, '#94a3b8')
        return format_html('<span style="color:{};font-weight:700;">{}</span>', color, obj.status)
    colored_status.short_description = 'Status'


# ── Profile ───────────────────────────────────────────────────────────────────
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


# ── ClassGroup ────────────────────────────────────────────────────────────────
@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display  = ('id', 'name', 'section')
    search_fields = ('name',)
    ordering      = ('name', 'section')


# ── Subject ───────────────────────────────────────────────────────────────────
@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display  = ('id', 'subject_name', 'class_group', 'teacher')
    list_filter   = ('class_group',)
    search_fields = ('subject_name',)


# ── QRSession ─────────────────────────────────────────────────────────────────
@admin.register(QRSession)
class QRSessionAdmin(admin.ModelAdmin):
    list_display  = ('session_id', 'created_by', 'date', 'expires_at', 'is_active', 'scan_count')
    list_filter   = ('is_active', 'date')
    ordering      = ('-created_at',)

    def scan_count(self, obj):
        return obj.scans.count()
    scan_count.short_description = 'Scans'


# ── Admin site branding ───────────────────────────────────────────────────────
admin.site.site_header = 'SAMS Administration'
admin.site.site_title  = 'SAMS Admin'
admin.site.index_title = 'School Attendance Management'
