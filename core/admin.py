from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from .models import Student, Course, Attendance, Profile


# ── Student ──────────────────────────────────────────────────────────────────
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display  = ('id', 'first_name', 'last_name', 'get_courses')
    list_display_links = ('id', 'first_name')
    search_fields = ('first_name', 'last_name')
    filter_horizontal = ('courses',)
    ordering      = ('id',)

    def get_courses(self, obj):
        return ', '.join([c.course_name for c in obj.courses.all()]) or '—'
    get_courses.short_description = 'Courses'


# ── Course ───────────────────────────────────────────────────────────────────
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display  = ('id', 'course_name', 'teacher')
    list_display_links = ('id', 'course_name')
    search_fields = ('course_name',)
    ordering      = ('id',)
    fields        = ('course_name', 'teacher')


# ── Attendance ────────────────────────────────────────────────────────────────
@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display  = ('id', 'student', 'course', 'date', 'status')
    list_filter   = ('status', 'course', 'date')
    search_fields = ('student__first_name', 'student__last_name')
    ordering      = ('-date',)


# ── Profile (Teacher/Admin roles) ─────────────────────────────────────────────
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'get_username', 'role')
    list_filter   = ('role',)
    search_fields = ('user__username', 'user__first_name')

    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = 'Username'


# ── Extend User admin to show ID + username ───────────────────────────────────
class CustomUserAdmin(UserAdmin):
    list_display = ('id', 'username', 'first_name', 'last_name', 'email', 'is_staff', 'get_role')
    list_display_links = ('id', 'username')
    ordering = ('id',)

    def get_role(self, obj):
        try:
            return obj.profile.role
        except Exception:
            return '—'
    get_role.short_description = 'Role'


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# Customize admin site header
admin.site.site_header  = 'SAMS Administration'
admin.site.site_title   = 'SAMS Admin'
admin.site.index_title  = 'School Attendance Management'
