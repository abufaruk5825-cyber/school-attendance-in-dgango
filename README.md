SAMS – School Attendance Management System

A Django-based web application for tracking, managing, and analyzing student attendance with role-based access control.


 Getting Started
 1. Install dependencies
  bash
pip install django


2. Apply migrations
   bash
python manage.py migrate
   
 3. Seed demo data
   bash
python seed.py

 4. Run the development server
    bash
python manage.py runserver

Visit: [http://127.0.0.1:8000](http://127.0.0.1:8000)

 🔐 Demo Login Credentials

 Admin
| Field    | Value      |
|----------|------------|
| Username | `admin`    |
| Password | `admin123` |

 Teachers
| Field    | Teacher 1    | Teacher 2    |
|----------|--------------|--------------|
| Username | `teacher1`   | `teacher2`   |
| Password | `teacher123` | `teacher123` |

 Students
Student accounts are created by the admin. Credentials are assigned during student account creation.

//  user nameseyna
// password  seid@1234

 //username sumi
// password  sumi@1234

 //username ss
// password  murad@12345


 👥 User Roles

| Role    | Access                                                                 |
|---------|------------------------------------------------------------------------|
| Admin   | Full access — manage students, teachers, courses, reports, settings    |
| Teacher | Mark attendance, view class reports, manage assigned courses           |
| Student | View personal attendance records and reports                           |



 Features

 Manage students, teachers, and courses
 Mark and track daily attendance
 QR code attendance scanning
 Generate detailed attendance reports (daily, monthly, date-wise, comparative)
 Role-based access control
 Dark / Light mode UI


📄 License
For educational use only.


// database show
1. Django Admin (easiest — already set up)
Run the server and go to http://127.0.0.1:8000/admin/