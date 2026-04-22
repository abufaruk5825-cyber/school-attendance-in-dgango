from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, HttpResponse
from .models import Student, Course, Subject, ClassGroup, Attendance, Profile, QRSession, QRScan
from django.contrib.auth.models import User
from django.utils import timezone
import datetime
import uuid
import qrcode
import io
import base64


def get_role(user):
    try:
        return user.profile.role
    except Exception:
        return None


def role_required(*roles):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if get_role(request.user) not in roles and not request.user.is_superuser:
                return HttpResponseForbidden("Access Denied")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def no_student(view_func):
    """Block student role from accessing a view — redirect to their dashboard."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if get_role(request.user) == 'student':
            return redirect('student_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        user = authenticate(request, username=request.POST['username'], password=request.POST['password'])
        if user:
            login(request, user)
            return redirect('home')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'login.html')


def landing(request):
    """Public landing page."""
    return render(request, 'landing.html')


def logout_view(request):
    logout(request)
    return redirect('login')


# ── Home / Dashboard ──────────────────────────────────────────────────────────

@login_required
def home(request):
    today = datetime.date.today()
    role = get_role(request.user)
    is_admin = request.user.is_superuser or role == 'admin'

    if is_admin:
        total_students = Student.objects.count()
        total_courses = Course.objects.count()
        present_today = Attendance.objects.filter(date=today, status='Present').count()
        absent_today = Attendance.objects.filter(date=today, status='Absent').count()
        total_today = present_today + absent_today
        pct = round((present_today / total_today * 100), 1) if total_today else 0
        recent = Attendance.objects.select_related('student', 'course').order_by('-date')[:20]
        my_courses = None
    else:
        # Teacher: only their assigned courses
        my_courses = Course.objects.filter(teacher=request.user)
        total_students = Student.objects.filter(courses__in=my_courses).distinct().count()
        total_courses = my_courses.count()
        present_today = Attendance.objects.filter(date=today, status='Present', course__in=my_courses).count()
        absent_today = Attendance.objects.filter(date=today, status='Absent', course__in=my_courses).count()
        total_today = present_today + absent_today
        pct = round((present_today / total_today * 100), 1) if total_today else 0
        recent = Attendance.objects.filter(course__in=my_courses).select_related('student', 'course').order_by('-date')[:20]

    # Student role: redirect to their own dashboard
    role = get_role(request.user)
    if role == 'student':
        try:
            student = request.user.student_profile
            return redirect('student_dashboard')
        except Exception:
            pass

    return render(request, 'home.html', {
        'total_students': total_students,
        'total_courses': total_courses,
        'present_today': present_today,
        'absent_today': absent_today,
        'attendance_pct': pct,
        'recent': recent,
        'today': today,
        'is_admin': is_admin,
        'my_courses': my_courses,
    })


# ── Students ──────────────────────────────────────────────────────────────────

@login_required
@no_student
def student_list(request):
    q = request.GET.get('q', '')
    course_filter = request.GET.get('course', '')
    students_qs = Student.objects.prefetch_related('courses')
    if q:
        students_qs = students_qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(student_id__icontains=q)
        )
    if course_filter:
        students_qs = students_qs.filter(courses__id=course_filter)

    # Compute attendance % for each student
    students = []
    for s in students_qs:
        total = Attendance.objects.filter(student=s).count()
        present = Attendance.objects.filter(student=s, status='Present').count()
        pct = round((present / total * 100), 1) if total else 0
        s.att_pct = pct
        s.att_total = total
        students.append(s)

    all_courses = Course.objects.all()
    return render(request, 'students/list.html', {
        'students': students, 'q': q,
        'all_courses': all_courses, 'course_filter': course_filter,
    })


@login_required
@login_required
@role_required('admin')
def student_create(request):
    import re
    courses = Course.objects.all()
    all_classes = ClassGroup.objects.all()
    if request.method == 'POST':
        student_id  = request.POST.get('student_id', '').strip()
        first_name  = request.POST.get('first_name', '').strip()
        last_name   = request.POST.get('last_name', '').strip()
        login_username = request.POST.get('login_username', '').strip()
        login_password = request.POST.get('login_password', '').strip()

        errors = []

        # First / Last name: letters and spaces only
        if not first_name:
            errors.append('First Name is required.')
        elif not re.fullmatch(r'[A-Za-z ]+', first_name):
            errors.append('First Name must contain letters only.')

        if not last_name:
            errors.append('Last Name is required.')
        elif not re.fullmatch(r'[A-Za-z ]+', last_name):
            errors.append('Last Name must contain letters only.')

        if not student_id:
            errors.append('Student ID is required.')
        elif Student.objects.filter(student_id=student_id).exists():
            errors.append(f'Student ID "{student_id}" already exists.')

        # Login account validation (only if provided)
        if login_username or login_password:
            if not login_username:
                errors.append('Username is required when creating a login.')
            elif not re.match(r'^[A-Za-z]', login_username):
                errors.append('Please insert correct username — must start with a letter (e.g. seya22).')
            elif not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', login_username):
                errors.append('Username can only contain letters and numbers, starting with a letter.')
            elif User.objects.filter(username=login_username).exists():
                errors.append(f'Username "{login_username}" already exists.')

            if not login_password:
                errors.append('Password is required when creating a login.')
            elif len(login_password) < 6:
                errors.append('Password must be at least 6 characters.')
            elif not re.search(r'[A-Za-z]', login_password):
                errors.append('Password must include at least one letter.')
            elif not re.search(r'\d', login_password):
                errors.append('Password must include at least one number.')
            elif not re.search(r'[!@#$%^&*()\-_=+\[\]{};\'\\:"|,.<>/?`~]', login_password):
                errors.append('Password must include at least one special character (e.g. @, #, !).')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'students/form.html', {'courses': courses, 'all_classes': all_classes, 'action': 'Add'})

        # Enforce max 30 students per class section
        class_group_id = request.POST.get('class_group') or None
        section = request.POST.get('section', '').strip()
        if class_group_id:
            current_count = Student.objects.filter(class_group_id=class_group_id).count()
            if current_count >= 30:
                cls_obj = ClassGroup.objects.filter(pk=class_group_id).first()
                messages.error(request, f'Class "{cls_obj}" already has 30 students. Maximum capacity reached.')
                return render(request, 'students/form.html', {'courses': courses, 'all_classes': all_classes, 'action': 'Add'})

        student = Student.objects.create(
            student_id=student_id,
            first_name=first_name,
            last_name=last_name,
            section=section,
            department=request.POST.get('department', '').strip(),
            parent_contact=request.POST.get('parent_contact', '').strip(),
            class_group_id=class_group_id,
        )
        course_ids = request.POST.getlist('courses')
        if course_ids:
            student.courses.set(course_ids)

        if login_username and login_password:
            login_user = User.objects.create_user(
                username=login_username,
                password=login_password,
                first_name=first_name,
                last_name=last_name
            )
            Profile.objects.filter(user=login_user).update(role='student')
            student.user = login_user
            student.save()
            messages.success(request, f'Student added with login: {login_username}')
        else:
            messages.success(request, 'Student added successfully.')
        return redirect('student_list')

    return render(request, 'students/form.html', {'courses': courses, 'all_classes': all_classes, 'action': 'Add'})


@login_required
@role_required('admin')
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)
    courses = Course.objects.all()
    all_classes = ClassGroup.objects.all()
    if request.method == 'POST':
        student_id = request.POST.get('student_id', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        if not student_id or not first_name or not last_name:
            messages.error(request, 'Student ID, First Name and Last Name are required.')
            assigned_ids = list(student.courses.values_list('id', flat=True))
            return render(request, 'students/form.html', {'student': student, 'courses': courses, 'all_classes': all_classes, 'assigned_ids': assigned_ids, 'action': 'Edit'})
        if Student.objects.filter(student_id=student_id).exclude(pk=pk).exists():
            messages.error(request, f'Student ID "{student_id}" already used by another student.')
            assigned_ids = list(student.courses.values_list('id', flat=True))
            return render(request, 'students/form.html', {'student': student, 'courses': courses, 'all_classes': all_classes, 'assigned_ids': assigned_ids, 'action': 'Edit'})
        student.student_id = student_id
        student.first_name = first_name
        student.last_name = last_name
        student.section = request.POST.get('section', '').strip()
        student.department = request.POST.get('department', '').strip()
        student.parent_contact = request.POST.get('parent_contact', '').strip()
        new_class_id = request.POST.get('class_group') or None
        # Enforce max 30 per class when changing class assignment
        if new_class_id and str(new_class_id) != str(student.class_group_id):
            current_count = Student.objects.filter(class_group_id=new_class_id).count()
            if current_count >= 30:
                cls_obj = ClassGroup.objects.filter(pk=new_class_id).first()
                messages.error(request, f'Class "{cls_obj}" already has 30 students. Maximum capacity reached.')
                assigned_ids = list(student.courses.values_list('id', flat=True))
                return render(request, 'students/form.html', {
                    'student': student, 'courses': courses, 'all_classes': all_classes,
                    'assigned_ids': assigned_ids, 'action': 'Edit'
                })
        student.class_group_id = new_class_id
        student.save()
        course_ids = request.POST.getlist('courses')
        student.courses.set(course_ids)
        messages.success(request, 'Student updated.')
        return redirect('student_list')
    assigned_ids = list(student.courses.values_list('id', flat=True))
    return render(request, 'students/form.html', {'student': student, 'courses': courses, 'all_classes': all_classes, 'assigned_ids': assigned_ids, 'action': 'Edit'})


@login_required
@role_required('admin')
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, 'Student deleted.')
        return redirect('student_list')
    return render(request, 'confirm_delete.html', {'obj': student, 'type': 'Student'})


@login_required
def student_detail(request, pk):
    # Students can only view their own profile
    role = get_role(request.user)
    if role == 'student':
        try:
            own = request.user.student_profile
            if own.pk != pk:
                return redirect('student_dashboard')
        except Exception:
            return redirect('student_dashboard')

    student = get_object_or_404(Student, pk=pk)
    records = Attendance.objects.filter(student=student).select_related('course', 'subject').order_by('-date')
    total = records.count()
    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    late = records.filter(status='Late').count()
    pct = round((present / total * 100), 1) if total else 0
    return render(request, 'students/detail.html', {
        'student': student, 'records': records,
        'total': total, 'present': present, 'absent': absent, 'late': late, 'pct': pct
    })


@login_required
def student_dashboard(request):
    """Dedicated dashboard for logged-in students — read-only view of own data."""
    role = get_role(request.user)
    if role not in ('student',) and not request.user.is_superuser:
        return redirect('home')
    try:
        student = request.user.student_profile
    except Exception:
        messages.error(request, 'No student profile linked to your account.')
        return redirect('login')

    records = Attendance.objects.filter(student=student).select_related('course', 'subject').order_by('-date')
    total = records.count()
    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    late = records.filter(status='Late').count()
    pct = round((present / total * 100), 1) if total else 0
    return render(request, 'students/dashboard.html', {
        'student': student, 'records': records,
        'total': total, 'present': present, 'absent': absent, 'late': late, 'pct': pct
    })


# ── Courses ───────────────────────────────────────────────────────────────────

@login_required
@no_student
def course_list(request):
    courses = Course.objects.annotate(student_count=Count('student')).select_related('teacher')
    return render(request, 'courses/list.html', {'courses': courses})


@login_required
@role_required('admin')
def course_create(request):
    teachers = User.objects.filter(profile__role='teacher')
    if request.method == 'POST':
        Course.objects.create(
            course_name=request.POST['course_name'],
            teacher_id=request.POST.get('teacher') or None,
        )
        messages.success(request, 'Course created.')
        return redirect('course_list')
    return render(request, 'courses/form.html', {'teachers': teachers, 'action': 'Add'})


@login_required
@role_required('admin')
def course_edit(request, pk):
    course = get_object_or_404(Course, pk=pk)
    teachers = User.objects.filter(profile__role='teacher')
    if request.method == 'POST':
        course.course_name = request.POST['course_name']
        course.teacher_id = request.POST.get('teacher') or None
        course.save()
        messages.success(request, 'Course updated.')
        return redirect('course_list')
    return render(request, 'courses/form.html', {'course': course, 'teachers': teachers, 'action': 'Edit'})


@login_required
@role_required('admin')
def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method == 'POST':
        course.delete()
        messages.success(request, 'Course deleted.')
        return redirect('course_list')
    return render(request, 'confirm_delete.html', {'obj': course, 'type': 'Course'})


# ── ClassGroup (Classes) ──────────────────────────────────────────────────────

@login_required
@role_required('admin')
def class_list(request):
    classes = ClassGroup.objects.annotate(
        student_count=Count('students'),
        subject_count=Count('subjects')
    ).order_by('name', 'section')
    return render(request, 'classes/list.html', {'classes': classes})


@login_required
@role_required('admin')
def class_create(request):
    grade_presets = [f'Grade {i}' for i in range(1, 13)]
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        section = request.POST.get('section', '').strip()
        if not name:
            messages.error(request, 'Class name is required.')
        elif ClassGroup.objects.filter(name=name, section=section).exists():
            messages.error(request, f'Class "{name} {section}" already exists.')
        else:
            ClassGroup.objects.create(name=name, section=section)
            messages.success(request, f'Class "{name}" created.')
            return redirect('class_list')
    return render(request, 'classes/form.html', {'action': 'Add', 'grade_presets': grade_presets})


@login_required
@role_required('admin')
def class_edit(request, pk):
    cls = get_object_or_404(ClassGroup, pk=pk)
    if request.method == 'POST':
        cls.name = request.POST.get('name', '').strip()
        cls.section = request.POST.get('section', '').strip()
        cls.save()
        messages.success(request, 'Class updated.')
        return redirect('class_list')
    return render(request, 'classes/form.html', {'cls': cls, 'action': 'Edit'})


@login_required
@role_required('admin')
def class_delete(request, pk):
    cls = get_object_or_404(ClassGroup, pk=pk)
    if request.method == 'POST':
        cls.delete()
        messages.success(request, 'Class deleted.')
        return redirect('class_list')
    return render(request, 'confirm_delete.html', {'obj': cls, 'type': 'Class'})


# ── Subjects ──────────────────────────────────────────────────────────────────

@login_required
@role_required('admin')
def subject_list(request):
    subjects = Subject.objects.select_related('class_group', 'teacher').order_by('class_group__name', 'subject_name')
    classes = ClassGroup.objects.all()
    class_filter = request.GET.get('class_group', '')
    if class_filter:
        subjects = subjects.filter(class_group_id=class_filter)
    return render(request, 'subjects/list.html', {
        'subjects': subjects, 'classes': classes, 'class_filter': class_filter
    })


@login_required
@role_required('admin')
def subject_create(request):
    classes = ClassGroup.objects.all()
    teachers = User.objects.filter(profile__role='teacher')
    if request.method == 'POST':
        name = request.POST.get('subject_name', '').strip()
        class_id = request.POST.get('class_group') or None
        teacher_id = request.POST.get('teacher') or None
        if not name:
            messages.error(request, 'Subject name is required.')
        else:
            Subject.objects.create(subject_name=name, class_group_id=class_id, teacher_id=teacher_id)
            messages.success(request, f'Subject "{name}" created.')
            return redirect('subject_list')
    return render(request, 'subjects/form.html', {'classes': classes, 'teachers': teachers, 'action': 'Add'})


@login_required
@role_required('admin')
def subject_edit(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    classes = ClassGroup.objects.all()
    teachers = User.objects.filter(profile__role='teacher')
    if request.method == 'POST':
        subject.subject_name = request.POST.get('subject_name', '').strip()
        subject.class_group_id = request.POST.get('class_group') or None
        subject.teacher_id = request.POST.get('teacher') or None
        subject.save()
        messages.success(request, 'Subject updated.')
        return redirect('subject_list')
    return render(request, 'subjects/form.html', {
        'subject': subject, 'classes': classes, 'teachers': teachers, 'action': 'Edit'
    })


@login_required
@role_required('admin')
def subject_delete(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        subject.delete()
        messages.success(request, 'Subject deleted.')
        return redirect('subject_list')
    return render(request, 'confirm_delete.html', {'obj': subject, 'type': 'Subject'})


# ── Attendance ────────────────────────────────────────────────────────────────

@login_required
@no_student
def attendance_mark(request):
    role = get_role(request.user)
    if role == 'teacher':
        courses = Course.objects.filter(teacher=request.user)
    else:
        courses = Course.objects.all()

    students = []
    selected_course = None
    selected_date = datetime.date.today().isoformat()

    # Collect filter params
    selected_section = request.GET.get('section', '')
    selected_department = request.GET.get('department', '')
    selected_month = request.GET.get('month', '')
    selected_year = request.GET.get('year', '')

    # Build distinct section lists and all classes for dropdowns
    all_sections = Student.objects.exclude(section__isnull=True).exclude(section='').values_list('section', flat=True).distinct().order_by('section')
    all_departments = Student.objects.exclude(department__isnull=True).exclude(department='').values_list('department', flat=True).distinct().order_by('department')
    current_year = datetime.date.today().year
    year_range = list(range(current_year - 4, current_year + 2))

    if request.method == 'GET' and request.GET.get('course'):
        selected_course = get_object_or_404(Course, pk=request.GET['course'])
        selected_date = request.GET.get('date', selected_date)

        # If month+year provided, use first day of that month as date
        if selected_month and selected_year:
            try:
                selected_date = datetime.date(int(selected_year), int(selected_month), 1).isoformat()
            except ValueError:
                pass

        # Get students enrolled in this course (old system) OR in the class linked to this course
        students = Student.objects.filter(courses=selected_course)

        # If no students found via old M2M, try class_group (new system)
        if not students.exists():
            students = Student.objects.all()

        # Apply section filter only if student has a section set
        if selected_section:
            students = students.filter(section__iexact=selected_section)

        # Apply grade/class filter via department field (now stores class name)
        if selected_department:
            students = students.filter(
                Q(department__iexact=selected_department) |
                Q(class_group__name__iexact=selected_department)
            )

        # Pre-fill existing records
        existing = {a.student_id: a.status for a in Attendance.objects.filter(course=selected_course, date=selected_date)}
        for s in students:
            s.existing_status = existing.get(s.id, '')

    if request.method == 'POST':
        course_id = request.POST.get('course')
        date = request.POST.get('date')
        selected_course = get_object_or_404(Course, pk=course_id)
        students_qs = Student.objects.filter(courses=selected_course)
        saved = 0
        for s in students_qs:
            status = request.POST.get(f'status_{s.id}')
            if status in ('Present', 'Absent', 'Late'):
                Attendance.objects.update_or_create(
                    student=s, course=selected_course, date=date,
                    defaults={'status': status}
                )
                saved += 1
        messages.success(request, f'Attendance saved for {saved} students.')
        return redirect('attendance_mark')

    return render(request, 'attendance/mark.html', {
        'courses': courses,
        'students': students,
        'selected_course': selected_course,
        'selected_date': selected_date,
        'selected_section': selected_section,
        'selected_department': selected_department,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'all_sections': all_sections,
        'all_departments': all_departments,
        'all_classes': ClassGroup.objects.all().order_by('name', 'section'),
        'year_range': year_range,
    })


@login_required
@no_student
def attendance_list(request):
    role = get_role(request.user)
    is_admin = request.user.is_superuser or role == 'admin'

    course_id = request.GET.get('course')
    student_id = request.GET.get('student')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    # Teachers see only their assigned subjects/courses
    if is_admin:
        courses = Course.objects.all()
        subjects = Subject.objects.select_related('class_group', 'teacher')
    else:
        courses = Course.objects.filter(teacher=request.user)
        subjects = Subject.objects.filter(teacher=request.user).select_related('class_group')

    # Teachers must select a course first
    if not is_admin and not course_id:
        return render(request, 'attendance/list.html', {
            'records': None, 'courses': courses, 'subjects': subjects, 'students': [],
            'course_id': '', 'student_id': '', 'date_from': '', 'date_to': '',
            'is_admin': is_admin, 'require_course': True,
        })

    records = Attendance.objects.select_related('student', 'course', 'subject').order_by('-date')

    # Restrict teacher to their courses only
    if not is_admin:
        records = records.filter(course__in=courses)

    if course_id:
        records = records.filter(course_id=course_id)
    if student_id:
        records = records.filter(student_id=student_id)
    if date_from:
        records = records.filter(date__gte=date_from)
    if date_to:
        records = records.filter(date__lte=date_to)

    # Students dropdown — filter by course if selected, else all
    if course_id:
        students = Student.objects.filter(courses__id=course_id).distinct()
    elif is_admin:
        students = Student.objects.all()
    else:
        students = Student.objects.filter(courses__in=courses).distinct()

    return render(request, 'attendance/list.html', {
        'records': records, 'courses': courses, 'subjects': subjects, 'students': students,
        'course_id': course_id, 'student_id': student_id,
        'date_from': date_from, 'date_to': date_to,
        'is_admin': is_admin, 'require_course': False,
    })


# ── Reports ───────────────────────────────────────────────────────────────────

@login_required
@no_student
def report_daily(request):
    date = request.GET.get('date', datetime.date.today().isoformat())
    course_id = request.GET.get('course')
    is_admin = request.user.is_superuser or get_role(request.user) == 'admin'

    if is_admin:
        courses = Course.objects.all()
    else:
        courses = Course.objects.filter(teacher=request.user)

    records = Attendance.objects.filter(date=date).select_related('student', 'course')

    # Teachers only see their own courses
    if not is_admin:
        records = records.filter(course__in=courses)

    if course_id:
        records = records.filter(course_id=course_id)

    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    total = present + absent
    pct = round((present / total * 100), 1) if total else 0
    return render(request, 'reports/daily.html', {
        'records': records, 'date': date, 'courses': courses,
        'present': present, 'absent': absent, 'total': total, 'pct': pct,
        'course_id': course_id, 'is_admin': is_admin,
    })


@login_required
@no_student
def report_monthly(request):
    month = request.GET.get('month', datetime.date.today().strftime('%Y-%m'))
    course_id = request.GET.get('course')
    is_admin = request.user.is_superuser or get_role(request.user) == 'admin'

    if is_admin:
        courses = Course.objects.all()
    else:
        courses = Course.objects.filter(teacher=request.user)

    try:
        year, mon = map(int, month.split('-'))
    except Exception:
        year, mon = datetime.date.today().year, datetime.date.today().month

    records = Attendance.objects.filter(date__year=year, date__month=mon).select_related('student', 'course')

    if not is_admin:
        records = records.filter(course__in=courses)

    if course_id:
        records = records.filter(course_id=course_id)

    student_ids = records.values_list('student_id', flat=True).distinct()
    summary = []
    for sid in student_ids:
        s_records = records.filter(student_id=sid)
        total = s_records.count()
        present = s_records.filter(status='Present').count()
        student = s_records.first().student
        summary.append({
            'student': student,
            'total': total,
            'present': present,
            'absent': total - present,
            'pct': round((present / total * 100), 1) if total else 0,
        })

    return render(request, 'reports/monthly.html', {
        'summary': summary, 'month': month, 'courses': courses, 'course_id': course_id,
    })


@login_required
@no_student
def report_datewise(request):
    course_id = request.GET.get('course')
    date = request.GET.get('date', datetime.date.today().isoformat())
    is_admin = request.user.is_superuser or get_role(request.user) == 'admin'

    if is_admin:
        courses = Course.objects.all()
    else:
        courses = Course.objects.filter(teacher=request.user)

    records = []
    selected_course = None
    if course_id:
        selected_course = get_object_or_404(Course, pk=course_id)
        records = Attendance.objects.filter(course_id=course_id, date=date).select_related('student')
        # Teacher can only view their own courses
        if not is_admin and not courses.filter(pk=course_id).exists():
            records = []
            selected_course = None

    return render(request, 'reports/datewise.html', {
        'records': records, 'courses': courses, 'course_id': course_id,
        'date': date, 'selected_course': selected_course,
    })


# ── Teachers ─────────────────────────────────────────────────────────────────

@login_required
@role_required('admin')
def teacher_list(request):
    teachers = User.objects.filter(profile__role='teacher').select_related('profile')
    return render(request, 'teachers/list.html', {'teachers': teachers})


@login_required
@login_required
@role_required('admin')
def teacher_create(request):
    import re
    from django.db import transaction
    courses = Course.objects.all()
    errors = []

    if request.method == 'POST':
        username   = request.POST.get('username', '').strip()
        password   = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        phone      = request.POST.get('phone', '').strip()
        address    = request.POST.get('address', '').strip()
        course_ids = request.POST.getlist('courses')

        # ── Validation ──────────────────────────────────────────
        # Username: must start with a letter, can contain letters and numbers
        if not username:
            errors.append('Username is required.')
        elif not re.match(r'^[A-Za-z]', username):
            errors.append('Please insert correct username — must start with a letter (e.g. seya22).')
        elif not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', username):
            errors.append('Username can only contain letters and numbers, starting with a letter.')
        elif User.objects.filter(username=username).exists():
            errors.append(f'Username "{username}" already exists.')

        # Password: min 6 chars, must have letter + digit + special char
        if not password:
            errors.append('Password is required.')
        elif len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        elif not re.search(r'[A-Za-z]', password):
            errors.append('Password must include at least one letter.')
        elif not re.search(r'\d', password):
            errors.append('Password must include at least one number.')
        elif not re.search(r'[!@#$%^&*()_+\-=\[\]{};\'\\:"|,.<>/?`~]', password):
            errors.append('Password must include at least one special character (e.g. @, #, !).')

        # Phone: Ethiopian format — +251XXXXXXXXX or 09XXXXXXXX or 07XXXXXXXX
        if phone:
            et_phone = re.fullmatch(r'(\+2519\d{8}|\+2517\d{8}|09\d{8}|07\d{8})', phone)
            if not et_phone:
                errors.append('Phone must be a valid Ethiopian number (e.g. +251912345678 or 0912345678).')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            try:
                with transaction.atomic():
                    # Step 1 — Create User
                    user = User.objects.create_user(
                        username=username,
                        password=password,
                        first_name=first_name,
                        last_name=last_name,
                    )
                    # Step 2 — Create Profile
                    Profile.objects.update_or_create(
                        user=user,
                        defaults={'role': 'teacher', 'phone': phone, 'address': address},
                    )
                    # Step 3 — Assign Courses
                    if course_ids:
                        Course.objects.filter(id__in=course_ids).update(teacher=user)

                messages.success(request, f'Teacher "{username}" registered successfully.')
                return redirect('teacher_list')
            except Exception as e:
                messages.error(request, f'Error creating teacher: {e}')

    return render(request, 'teachers/form.html', {'courses': courses})


@login_required
@role_required('admin')
def teacher_edit(request, pk):
    teacher = get_object_or_404(User, pk=pk)
    all_courses = Course.objects.all()
    assigned_ids = list(Course.objects.filter(teacher=teacher).values_list('id', flat=True))
    if request.method == 'POST':
        course_ids = request.POST.getlist('courses')
        # Unassign all current courses for this teacher
        Course.objects.filter(teacher=teacher).update(teacher=None)
        # Assign newly selected courses
        if course_ids:
            Course.objects.filter(id__in=course_ids).update(teacher=teacher)
        messages.success(request, f'Courses updated for {teacher.username}.')
        return redirect('teacher_list')
    return render(request, 'teachers/edit.html', {
        'teacher': teacher,
        'courses': all_courses,
        'assigned_ids': assigned_ids,
    })


@login_required
@role_required('admin')
def teacher_delete(request, pk):
    teacher = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        teacher.delete()
        messages.success(request, 'Teacher deleted.')
        return redirect('teacher_list')
    return render(request, 'confirm_delete.html', {'obj': teacher, 'type': 'Teacher'})


@login_required
@no_student
def report_comparative(request):
    students = Student.objects.all()
    summary = []
    for s in students:
        records = Attendance.objects.filter(student=s)
        total = records.count()
        present = records.filter(status='Present').count()
        summary.append({
            'student': s,
            'total': total,
            'present': present,
            'absent': total - present,
            'pct': round((present / total * 100), 1) if total else 0,
        })
    summary.sort(key=lambda x: x['pct'])
    return render(request, 'reports/comparative.html', {'summary': summary})


# ── Settings ──────────────────────────────────────────────────────────────────

@login_required
@role_required('admin')
def settings_view(request):
    teachers = User.objects.filter(profile__role='teacher').select_related('profile')
    admins   = User.objects.filter(profile__role='admin').select_related('profile')
    students = User.objects.filter(profile__role='student').select_related('profile')
    return render(request, 'settings.html', {
        'teachers': teachers,
        'admins':   admins,
        'students': students,
    })


# ── Student Self-Service Views ────────────────────────────────────────────────

@login_required
def student_attendance_view(request):
    """Student views their own attendance records with filters."""
    role = get_role(request.user)
    if role != 'student':
        return redirect('home')
    try:
        student = request.user.student_profile
    except Exception:
        return redirect('login')

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    subject_filter = request.GET.get('subject', '')

    records = Attendance.objects.filter(student=student).select_related('course', 'subject').order_by('-date')
    if date_from:
        records = records.filter(date__gte=date_from)
    if date_to:
        records = records.filter(date__lte=date_to)
    if subject_filter:
        records = records.filter(
            Q(course__course_name__icontains=subject_filter) |
            Q(subject__subject_name__icontains=subject_filter)
        )

    total = records.count()
    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    late = records.filter(status='Late').count()
    pct = round((present / total * 100), 1) if total else 0

    courses = Course.objects.filter(student__user=request.user)
    subjects = Subject.objects.filter(class_group=student.class_group) if student.class_group else Subject.objects.none()

    return render(request, 'students/attendance.html', {
        'student': student, 'records': records,
        'total': total, 'present': present, 'absent': absent, 'late': late, 'pct': pct,
        'date_from': date_from, 'date_to': date_to, 'subject_filter': subject_filter,
        'courses': courses, 'subjects': subjects,
    })


@login_required
def student_reports_view(request):
    """Student views their own reports and statistics."""
    role = get_role(request.user)
    if role != 'student':
        return redirect('home')
    try:
        student = request.user.student_profile
    except Exception:
        return redirect('login')

    records = Attendance.objects.filter(student=student).select_related('course', 'subject').order_by('-date')
    total = records.count()
    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    late = records.filter(status='Late').count()
    pct = round((present / total * 100), 1) if total else 0

    from django.db.models.functions import TruncMonth
    from django.db.models import Count
    monthly = []
    months_qs = records.annotate(month=TruncMonth('date')).values('month').annotate(
        total=Count('id'),
        present_count=Count('id', filter=Q(status='Present'))
    ).order_by('-month')[:6]
    for m in months_qs:
        t = m['total']
        p = m['present_count']
        monthly.append({
            'month': m['month'].strftime('%B %Y') if m['month'] else '',
            'total': t,
            'present': p,
            'absent': t - p,
            'pct': round((p / t * 100), 1) if t else 0,
        })

    subject_stats = []
    for course in Course.objects.filter(attendance__student=student).distinct():
        r = records.filter(course=course)
        t = r.count()
        p = r.filter(status='Present').count()
        subject_stats.append({
            'name': course.course_name,
            'total': t, 'present': p,
            'pct': round((p / t * 100), 1) if t else 0,
        })
    for subj in Subject.objects.filter(attendance__student=student).distinct():
        r = records.filter(subject=subj)
        t = r.count()
        p = r.filter(status='Present').count()
        subject_stats.append({
            'name': subj.subject_name,
            'total': t, 'present': p,
            'pct': round((p / t * 100), 1) if t else 0,
        })

    return render(request, 'students/reports.html', {
        'student': student, 'total': total, 'present': present,
        'absent': absent, 'late': late, 'pct': pct,
        'monthly': monthly, 'subject_stats': subject_stats,
    })


@login_required
def student_profile_view(request):
    """Student views and updates their own profile."""
    role = get_role(request.user)
    if role != 'student':
        return redirect('home')
    try:
        student = request.user.student_profile
    except Exception:
        return redirect('login')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'change_password':
            old_pw = request.POST.get('old_password', '')
            new_pw = request.POST.get('new_password', '')
            confirm_pw = request.POST.get('confirm_password', '')
            if not request.user.check_password(old_pw):
                messages.error(request, 'Current password is incorrect.')
            elif new_pw != confirm_pw:
                messages.error(request, 'New passwords do not match.')
            elif len(new_pw) < 6:
                messages.error(request, 'Password must be at least 6 characters.')
            else:
                request.user.set_password(new_pw)
                request.user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password changed successfully.')
        return redirect('student_profile')

    return render(request, 'students/profile.html', {'student': student})


# ── Student Login Management ──────────────────────────────────────────────────

@login_required
@role_required('admin')
def student_create_login(request, pk):
    import re
    student = get_object_or_404(Student, pk=pk)
    if student.user:
        messages.warning(request, f'{student} already has a login account.')
        return redirect('student_detail', pk=pk)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        errors = []

        if not username:
            errors.append('Username is required.')
        elif not re.match(r'^[A-Za-z]', username):
            errors.append('Please insert correct username — must start with a letter (e.g. seya22).')
        elif not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', username):
            errors.append('Username can only contain letters and numbers, starting with a letter.')
        elif User.objects.filter(username=username).exists():
            errors.append(f'Username "{username}" already exists.')

        if not password:
            errors.append('Password is required.')
        elif len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        elif not re.search(r'[A-Za-z]', password):
            errors.append('Password must include at least one letter.')
        elif not re.search(r'\d', password):
            errors.append('Password must include at least one number.')
        elif not re.search(r'[!@#$%^&*()\-_=+\[\]{};\'\\:"|,.<>/?`~]', password):
            errors.append('Password must include at least one special character (e.g. @, #, !).')

        if errors:
            for e in errors:
                messages.error(request, e)
            return redirect('student_detail', pk=pk)

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=student.first_name,
            last_name=student.last_name
        )
        Profile.objects.filter(user=user).update(role='student')
        student.user = user
        student.save()
        messages.success(request, f'Login created for {student}. Username: {username}')
        return redirect('student_detail', pk=pk)

    return redirect('student_detail', pk=pk)


# ── Student Role Pages ────────────────────────────────────────────────────────

@login_required
def student_attendance_view(request):
    """Student views their own attendance records with filters."""
    if get_role(request.user) != 'student':
        return redirect('home')
    try:
        student = request.user.student_profile
    except Exception:
        return redirect('login')

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    subject_filter = request.GET.get('subject', '')

    records = Attendance.objects.filter(student=student).select_related('course', 'subject').order_by('-date')
    if date_from:
        records = records.filter(date__gte=date_from)
    if date_to:
        records = records.filter(date__lte=date_to)
    if subject_filter:
        records = records.filter(
            Q(course__course_name__icontains=subject_filter) |
            Q(subject__subject_name__icontains=subject_filter)
        )

    total = records.count()
    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    late = records.filter(status='Late').count()
    pct = round((present / total * 100), 1) if total else 0

    courses = Course.objects.filter(attendance__student=student).distinct()
    subjects = Subject.objects.filter(class_group=student.class_group) if student.class_group else Subject.objects.none()

    return render(request, 'students/attendance.html', {
        'student': student, 'records': records,
        'total': total, 'present': present, 'absent': absent, 'late': late, 'pct': pct,
        'date_from': date_from, 'date_to': date_to, 'subject_filter': subject_filter,
        'courses': courses, 'subjects': subjects,
    })


@login_required
def student_reports_view(request):
    """Student views their own reports and statistics."""
    if get_role(request.user) != 'student':
        return redirect('home')
    try:
        student = request.user.student_profile
    except Exception:
        return redirect('login')

    from django.db.models.functions import TruncMonth

    records = Attendance.objects.filter(student=student).select_related('course', 'subject').order_by('-date')
    total = records.count()
    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    late = records.filter(status='Late').count()
    pct = round((present / total * 100), 1) if total else 0

    # Monthly summary (last 6 months)
    monthly = []
    months_qs = records.annotate(month=TruncMonth('date')).values('month').annotate(
        total=Count('id'),
        present_count=Count('id', filter=Q(status='Present'))
    ).order_by('-month')[:6]
    for m in months_qs:
        t = m['total']
        p = m['present_count']
        monthly.append({
            'month': m['month'].strftime('%B %Y') if m['month'] else '',
            'total': t, 'present': p, 'absent': t - p,
            'pct': round((p / t * 100), 1) if t else 0,
        })

    # Subject-wise breakdown
    subject_stats = []
    for course in Course.objects.filter(attendance__student=student).distinct():
        r = records.filter(course=course)
        t = r.count()
        p = r.filter(status='Present').count()
        subject_stats.append({'name': course.course_name, 'total': t, 'present': p,
                               'pct': round((p / t * 100), 1) if t else 0})
    for subj in Subject.objects.filter(attendance__student=student).distinct():
        r = records.filter(subject=subj)
        t = r.count()
        p = r.filter(status='Present').count()
        subject_stats.append({'name': subj.subject_name, 'total': t, 'present': p,
                               'pct': round((p / t * 100), 1) if t else 0})

    return render(request, 'students/reports.html', {
        'student': student, 'total': total, 'present': present,
        'absent': absent, 'late': late, 'pct': pct,
        'monthly': monthly, 'subject_stats': subject_stats,
    })


@login_required
def student_profile_view(request):
    """Student views and updates their own profile."""
    if get_role(request.user) != 'student':
        return redirect('home')
    try:
        student = request.user.student_profile
    except Exception:
        return redirect('login')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'change_password':
            old_pw = request.POST.get('old_password', '')
            new_pw = request.POST.get('new_password', '')
            confirm_pw = request.POST.get('confirm_password', '')
            if not request.user.check_password(old_pw):
                messages.error(request, 'Current password is incorrect.')
            elif new_pw != confirm_pw:
                messages.error(request, 'New passwords do not match.')
            elif len(new_pw) < 6:
                messages.error(request, 'Password must be at least 6 characters.')
            else:
                request.user.set_password(new_pw)
                request.user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password changed successfully.')
        return redirect('student_profile')

    return render(request, 'students/profile.html', {'student': student})

# ── QR Code Attendance ────────────────────────────────────────────────────────

def _make_qr_image_b64(url):
    """Generate a QR code image and return as base64 string."""
    qr = qrcode.QRCode(version=1, box_size=8, border=4,
                       error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


@login_required
@no_student
def qr_generate(request):
    """Teacher/Admin generates a QR session."""
    role = get_role(request.user)
    is_admin = request.user.is_superuser or role == 'admin'

    if is_admin:
        courses = Course.objects.all()
        subjects = Subject.objects.select_related('class_group')
        classes = ClassGroup.objects.all()
    else:
        courses = Course.objects.filter(teacher=request.user)
        subjects = Subject.objects.filter(teacher=request.user).select_related('class_group')
        classes = ClassGroup.objects.filter(
            Q(subjects__teacher=request.user) | Q(students__courses__teacher=request.user)
        ).distinct()

    session = None
    qr_b64 = None
    scan_url = None

    if request.method == 'POST':
        course_id = request.POST.get('course') or None
        subject_id = request.POST.get('subject') or None
        class_id = request.POST.get('class_group') or None
        minutes = int(request.POST.get('minutes', 10))
        minutes = max(1, min(minutes, 60))  # clamp 1–60

        expires = timezone.now() + datetime.timedelta(minutes=minutes)
        session = QRSession.objects.create(
            course_id=course_id,
            subject_id=subject_id,
            class_group_id=class_id,
            created_by=request.user,
            date=datetime.date.today(),
            expires_at=expires,
        )

        # Build the scan URL
        scan_url = request.build_absolute_uri(f'/attendance/qr/scan/{session.session_id}/')
        qr_b64 = _make_qr_image_b64(scan_url)

    # List recent sessions created by this user
    recent_sessions = QRSession.objects.filter(created_by=request.user).order_by('-created_at')[:10]

    return render(request, 'attendance/qr_generate.html', {
        'courses': courses,
        'subjects': subjects,
        'classes': classes,
        'session': session,
        'qr_b64': qr_b64,
        'scan_url': scan_url,
        'recent_sessions': recent_sessions,
        'is_admin': is_admin,
    })


@login_required
@no_student
def qr_session_toggle(request, session_id):
    """Deactivate/reactivate a QR session."""
    session = get_object_or_404(QRSession, session_id=session_id, created_by=request.user)
    session.is_active = not session.is_active
    session.save()
    status = "activated" if session.is_active else "deactivated"
    messages.success(request, f'Session {status}.')
    return redirect('qr_generate')


@login_required
def qr_scan(request, session_id):
    """Student scans QR → this view marks their attendance."""
    # Only students (or admins testing) can scan
    role = get_role(request.user)

    session = get_object_or_404(QRSession, session_id=session_id)

    # Validate session
    if not session.is_valid():
        return render(request, 'attendance/qr_result.html', {
            'success': False,
            'message': 'This QR code has expired or been deactivated. Ask your teacher to generate a new one.',
        })

    # Get student profile
    try:
        student = request.user.student_profile
    except Exception:
        # Admin/teacher scanning for testing
        if request.user.is_superuser or role in ('admin', 'teacher'):
            return render(request, 'attendance/qr_result.html', {
                'success': False,
                'message': 'QR session is valid. (Staff accounts cannot mark attendance via QR.)',
                'session': session,
            })
        return render(request, 'attendance/qr_result.html', {
            'success': False,
            'message': 'No student profile linked to your account. Contact your admin.',
        })

    # Prevent duplicate scan
    if QRScan.objects.filter(session=session, student=student).exists():
        return render(request, 'attendance/qr_result.html', {
            'success': False,
            'message': 'You have already scanned this QR code. Attendance already recorded.',
            'already_scanned': True,
        })

    # Mark attendance
    att_kwargs = dict(student=student, date=session.date, defaults={'status': 'Present'})
    if session.course_id:
        att_kwargs['course_id'] = session.course_id
    if session.subject_id:
        att_kwargs['subject_id'] = session.subject_id

    Attendance.objects.update_or_create(**att_kwargs)
    QRScan.objects.create(session=session, student=student)

    return render(request, 'attendance/qr_result.html', {
        'success': True,
        'message': f'Attendance marked as Present for {student.first_name} {student.last_name}!',
        'student': student,
        'session': session,
    })


@login_required
@no_student
def qr_session_detail(request, session_id):
    """Admin/Teacher views who scanned a session."""
    session = get_object_or_404(QRSession, session_id=session_id)
    role = get_role(request.user)
    is_admin = request.user.is_superuser or role == 'admin'
    if not is_admin and session.created_by != request.user:
        return HttpResponseForbidden("Access Denied")

    scans = QRScan.objects.filter(session=session).select_related('student').order_by('scanned_at')
    scan_url = request.build_absolute_uri(f'/attendance/qr/scan/{session.session_id}/')
    qr_b64 = _make_qr_image_b64(scan_url)

    return render(request, 'attendance/qr_session_detail.html', {
        'session': session,
        'scans': scans,
        'qr_b64': qr_b64,
        'scan_url': scan_url,
        'is_valid': session.is_valid(),
    })
