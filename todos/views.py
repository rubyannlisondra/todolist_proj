from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from datetime import date, timedelta
from .models import Todo, Category, TodoHistory, UserProfile, Subtask, SharedTask, SharedTaskCompletion, SharedTaskComment
from .forms import TodoForm, CategoryForm, UserProfileForm, UserUpdateForm, SubtaskForm, SharedTaskForm, SharedTaskCommentForm
import todos
from .models import Todo, Category, TodoHistory, UserProfile, Subtask
from .forms import TodoForm, CategoryForm, UserProfileForm, UserUpdateForm, SubtaskForm
from functools import wraps
from django.http import HttpResponse, JsonResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.units import cm
from collections import defaultdict
import json
from django.contrib.auth.models import User
from todos import models

def regular_user_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_superuser or request.user.is_staff:
            messages.error(request, 'Admin accounts must use the Admin Panel.')
            logout(request)
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper

def register_view(request):
    if request.user.is_authenticated and not request.user.is_superuser:
        return redirect('index')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Prevent superuser registration from this form
            if user.is_superuser or user.is_staff:
                user.delete()
                messages.error(request, 'Admin accounts cannot be registered here.')
                return redirect('register')
            messages.success(request, 'Account created successfully! Please log in.')
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'todos/register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.is_staff:
            logout(request)
            messages.error(request, 'Please use the Admin Panel to log in as admin.')
            return redirect('login')
        return redirect('index')

    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.is_superuser or user.is_staff:
                return redirect('login')
            login(request, user)
            messages.success(request, 'Logged in successfully!')
            return redirect('index')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    return render(request, 'todos/login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully!')
    return redirect('login')

@regular_user_required
def index(request):
    today = date.today()
    tab = request.GET.get('tab', 'all')
    category_filter = request.GET.get('category')
    search_query = request.GET.get('search', '')
    sort_by = request.GET.get('sort', '-created_at')

    todos = Todo.objects.filter(user=request.user, is_deleted=False, is_archived=False)

    if tab == 'today':
        todos = todos.filter(due_date=today)
    elif tab == 'upcoming':
        todos = todos.filter(due_date__gt=today)
    elif tab == 'overdue':
        todos = todos.filter(due_date__lt=today, completed=False)

    if category_filter:
        todos = todos.filter(category__id=category_filter)

    if search_query:
        todos = todos.filter(Q(title__icontains=search_query))

    valid_sorts = ['-created_at', 'created_at', 'due_date', '-priority', 'title']
    if sort_by in valid_sorts:
        todos = todos.order_by(sort_by)
    else:
        todos = todos.order_by('-created_at')

    categories = Category.objects.filter(user=request.user)
    todo_form = TodoForm(user=request.user)
    category_form = CategoryForm()

    all_todos = Todo.objects.filter(user=request.user, is_deleted=False, is_archived=False)
    total = all_todos.count()
    completed_count = all_todos.filter(completed=True).count()
    overdue_count = all_todos.filter(due_date__lt=today, completed=False).count()

    return render(request, 'todos/index.html', {
        'todos': todos,
        'categories': categories,
        'todo_form': todo_form,
        'category_form': category_form,
        'selected_category': category_filter,
        'tab': tab,
        'search_query': search_query,
        'sort_by': sort_by,
        'total': total,
        'completed_count': completed_count,
        'overdue_count': overdue_count,
        'today': today,
    })

@regular_user_required
def add_todo(request):
    if request.method == 'POST':
        form = TodoForm(request.POST, user=request.user)
        if form.is_valid():
            todo = form.save(commit=False)
            todo.user = request.user
            todo.save()
            TodoHistory.objects.create(
                todo=todo,
                changed_by=request.user,
                change_description=f'Task "{todo.title}" was created.'
            )
            messages.success(request, 'Task added successfully!')
    return redirect('index')

@regular_user_required
def edit_todo(request, pk):
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    if request.method == 'POST':
        form = TodoForm(request.POST, instance=todo, user=request.user)
        if form.is_valid():
            form.save()
            TodoHistory.objects.create(
                todo=todo,
                changed_by=request.user,
                change_description=f'Task "{todo.title}" was edited.'
            )
            messages.success(request, 'Task updated successfully!')
            return redirect('index')
    else:
        form = TodoForm(instance=todo, user=request.user)
    subtasks = todo.subtasks.all()
    subtask_form = SubtaskForm()
    return render(request, 'todos/edit_todo.html', {
        'form': form,
        'todo': todo,
        'subtasks': subtasks,
        'subtask_form': subtask_form,
    })

@regular_user_required
def add_subtask(request, pk):
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    if request.method == 'POST':
        form = SubtaskForm(request.POST)
        if form.is_valid():
            subtask = form.save(commit=False)
            subtask.todo = todo
            subtask.save()
            messages.success(request, 'Subtask added!')
    return redirect('edit_todo', pk=pk)

@regular_user_required
def toggle_subtask(request, pk):
    subtask = get_object_or_404(Subtask, pk=pk, todo__user=request.user)
    subtask.completed = not subtask.completed
    subtask.save()
    return redirect('edit_todo', pk=subtask.todo.pk)

@regular_user_required
def delete_subtask(request, pk):
    subtask = get_object_or_404(Subtask, pk=pk, todo__user=request.user)
    todo_pk = subtask.todo.pk
    subtask.delete()
    return redirect('edit_todo', pk=todo_pk)

@regular_user_required
def toggle_todo(request, pk):
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    todo.completed = not todo.completed
    todo.save()

    if todo.completed and todo.recurrence != 'none':
        today = date.today()
        if todo.recurrence == 'daily':
            new_due = today + timedelta(days=1)
        elif todo.recurrence == 'weekly':
            new_due = today + timedelta(weeks=1)
        elif todo.recurrence == 'monthly':
            new_due = today.replace(month=today.month % 12 + 1)
        else:
            new_due = today

        Todo.objects.create(
            user=request.user,
            title=todo.title,
            category=todo.category,
            priority=todo.priority,
            recurrence=todo.recurrence,
            due_date=new_due,
        )
        messages.success(request, f'Recurring task scheduled for {new_due}!')

    status = 'completed' if todo.completed else 'marked as incomplete'
    TodoHistory.objects.create(
        todo=todo,
        changed_by=request.user,
        change_description=f'Task "{todo.title}" was {status}.'
    )
    return redirect('index')

@regular_user_required
def delete_todo(request, pk):
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    todo.is_deleted = True
    todo.deleted_at = timezone.now()
    todo.save()
    TodoHistory.objects.create(
        todo=todo,
        changed_by=request.user,
        change_description=f'Task "{todo.title}" was deleted.'
    )
    messages.success(request, 'Task moved to trash!')
    return redirect('index')

@regular_user_required
def archive_todo(request, pk):
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    todo.is_archived = True
    todo.save()
    messages.success(request, 'Task archived!')
    return redirect('index')

@regular_user_required
def archived_tasks(request):
    todos = Todo.objects.filter(user=request.user, is_archived=True, is_deleted=False)
    return render(request, 'todos/archived.html', {'todos': todos})

@regular_user_required
def deleted_tasks(request):
    todos = Todo.objects.filter(user=request.user, is_deleted=True)
    return render(request, 'todos/deleted.html', {'todos': todos})

@regular_user_required
def restore_todo(request, pk):
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    todo.is_deleted = False
    todo.is_archived = False
    todo.deleted_at = None
    todo.save()
    messages.success(request, 'Task restored successfully!')
    return redirect('deleted_tasks')

@regular_user_required
def permanent_delete(request, pk):
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    todo.delete()
    messages.success(request, 'Task permanently deleted!')
    return redirect('deleted_tasks')

@regular_user_required
def add_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, 'Category added!')
    return redirect('index')

@regular_user_required
def delete_category(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    category.delete()
    messages.success(request, 'Category deleted successfully!')
    return redirect('index')

@regular_user_required
def profile_view(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = UserProfileForm(instance=profile)
    return render(request, 'todos/profile.html', {
        'user_form': user_form,
        'profile_form': profile_form,
    })

@regular_user_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'todos/change_password.html', {'form': form})

@regular_user_required
def task_history(request):
    todos = Todo.objects.filter(user=request.user)
    history = TodoHistory.objects.filter(todo__in=todos).order_by('-changed_at')
    return render(request, 'todos/history.html', {'history': history})

@regular_user_required
def analytics_view(request):
    today = date.today()
    user = request.user
    
    all_todos = Todo.objects.filter(user=user, is_deleted=False)
    active_todos = all_todos.filter(is_archived=False)

    total = active_todos.count()
    completed = active_todos.filter(completed=True).count()
    overdue = active_todos.filter(due_date__lt=today, completed=False).count()
    pending = active_todos.filter(completed=False).count()
    completion_rate = round((completed / total * 100), 1) if total > 0 else 0

    streak = 0
    check_date = today
    while True:
        completed_on_day = all_todos.filter(completed=True, updated_at__date=check_date).exists()

        if completed_on_day:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    score = 0
    if total > 0:
        score += completion_rate * 0.5
        score += min(streak * 5, 30)
        score += min(overdue * 3, 20)
        score += max(0, min(100, round(score)))

    daily_labels = []
    daily_completed = []
    daily_created = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        daily_labels.append(day.strftime('%b %d'))
        daily_completed.append(all_todos.filter(completed=True, updated_at__date=day).count())
        daily_created.append(all_todos.filter(created_at__date=day).count())

    weekly_labels = []
    weekly_completed = []
    for i in range(7, -1, -1):
        week_start = today - timedelta(weeks=i, days=today.weekday())
        week_end = week_start + timedelta(days=6)
        weekly_labels.append(f'Wk {week_start.strftime("%b %d")}')
        weekly_completed.append(all_todos.filter(completed=True, updated_at__date__range=[week_start, week_end]).count())

    categories = Category.objects.filter(user=user)
    category_data = []
    for cat in categories:
        cat_total = active_todos.filter(category=cat).count()
        cat_done = active_todos.filter(category=cat, completed=True).count()
        if cat_total > 0:
            category_data.append({
                'name': cat.name,
                'total': cat_total,
                'completed': cat_done,
                'rate': round(cat_done / cat_total * 100, 1),
            })

    priority_data = []
    for priority, label in [('urgent', 'Urgent'), ('high', 'High'), ('medium', 'Medium'), ('low', 'Low')]:
        count = active_todos.filter(priority=priority).count()
        done = active_todos.filter(priority=priority, completed=True).count()
        priority_data.append({
            'priority': label,
            'total': count,
            'completed': done,
        })

        context = {
            'total': total,
            'completed': completed,
            'overdue': overdue,
            'pending': pending,
            'completion_rate': completion_rate,
            'streak': streak,
            'score': score,
            'daily_labels': json.dumps(daily_labels),
            'daily_completed': json.dumps(daily_completed),
            'daily_created': json.dumps(daily_created),
            'weekly_labels': json.dumps(weekly_labels),
            'weekly_completed': json.dumps(weekly_completed),
            'category_data': category_data,
            'priority_data': priority_data,
            'today': today,
        }
        return render(request, 'todos/analytics.html', context)
    
@regular_user_required
def export_report(request):
    today = date.today()
    user = request.user

    all_todos = Todo.objects.filter(user=user, is_deleted=False)
    active_todos = all_todos.filter(is_archived=False)

    total = active_todos.count()
    completed = active_todos.filter(completed=True).count()
    overdue = active_todos.filter(due_date__lt=today, completed=False).count()
    pending = active_todos.filter(completed=False).count()
    completion_rate = round((completed / total * 100), 1) if total > 0 else 0

    streak = 0
    check_date = today
    while True:
        if all_todos.filter(completed=True, updated_at__date=check_date).exists():
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    score = 0
    if total > 0:
        score += completion_rate * 0.5
        score += min(streak * 5, 30)
        score += min(overdue * 3, 20)
        score += max(0, min(100, round(score)))

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="task_report_{today}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(
        'Title', parent=styles['Title'],
        fontSize=24, textColor=colors.HexColor('#2d4a5f'),
        spaceAfter=4, fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontSize=11, textColor=colors.HexColor('#6a9bbf'),
        spaceAfter=20
    )

    heading_style = ParagraphStyle(
        'Heading', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor('#2d4a5f'),
        spaceBefore=16, spaceAfter=8, fontName='Helvetica-Bold'
    )
    normal_style = ParagraphStyle(
        'Normal2', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#444444'),
        spaceAfter=4
    )

    elements.append(Paragraph('📝 Taskly', title_style))
    elements.append(Paragraph(f'Productivity Report - {today.strftime("%B %d, %Y")}', subtitle_style))
    elements.append(Paragraph(f'Generated for: {user.username}', normal_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#a8cce0'), spaceBefore=16))

    elements.append(Paragraph('Summary Overview', heading_style))
    summary_data = [
        ['Metric', 'Value'],
        ['Total Tasks', str(total)],
        ['Completed Tasks', str(completed)],
        ['Pending Tasks', str(pending)],
        ['Overdue Tasks', str(overdue)],
        ['Completion Rate', f'{completion_rate}%'],
        ['Current Streak', f'{streak} day(s)'],
        ['Productivity Score', f'{score}/100'],
    ]
    summary_table = Table(summary_data, colWidths=[9*cm, 7*cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d4a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.HexColor('#f0f7fc'), colors.white]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#ddeaf3')),
        ('ROWHEIGHT', (0, 0), (-1, -1), 28),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 16))

    # ── Priority Breakdown ──
    elements.append(HRFlowable(width="100%", thickness=1,
                               color=colors.HexColor('#ddeaf3'), spaceAfter=8))
    elements.append(Paragraph('Tasks by Priority', heading_style))
    priority_table_data = [['Priority', 'Total', 'Completed', 'Pending']]
    for priority, label in [('urgent', 'Urgent'), ('high', 'High'),
                             ('medium', 'Medium'), ('low', 'Low')]:
        p_total = active_todos.filter(priority=priority).count()
        p_done = active_todos.filter(priority=priority, completed=True).count()
        priority_table_data.append([label, str(p_total),
                                    str(p_done), str(p_total - p_done)])
    priority_table = Table(priority_table_data,
                           colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
    priority_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6a9bbf')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.HexColor('#f0f7fc'), colors.white]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#ddeaf3')),
        ('ROWHEIGHT', (0, 0), (-1, -1), 26),
    ]))
    elements.append(priority_table)
    elements.append(Spacer(1, 16))

    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#ddeaf3'), spaceAfter=8))
    elements.append(Paragraph('Tasks by Category', heading_style))
    categories = Category.objects.filter(user=user)
    cat_table_data = [['Category', 'Total', 'Completed', 'Rate']]
    for cat in categories:
        c_total = active_todos.filter(category=cat).count()
        c_done = active_todos.filter(category=cat, completed=True).count()
        c_rate = f'{round(c_done/c_total*100, 1)}%' if c_total > 0 else '0%'
        cat_table_data.append([cat.name, str(c_total), str(c_done), c_rate])
    if len(cat_table_data) > 1:
        cat_table = Table(cat_table_data, colWidths=[5*cm, 3.5*cm, 3.5*cm, 4*cm])
        cat_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6a9bbf')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.HexColor('#f0f7fc'), colors.white]),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#ddeaf3')),
            ('ROWHEIGHT', (0, 0), (-1, -1), 26),
        ]))
        elements.append(cat_table)
    else:
        elements.append(Paragraph('No categories found.', normal_style))

    elements.append(Spacer(1, 16))
    elements.append(HRFlowable(width="100%", thickness=1,
                               color=colors.HexColor('#ddeaf3'), spaceAfter=8))
    elements.append(Paragraph('Daily Trend (Last 14 Days)', heading_style))
    trend_data = [['Date', 'Created', 'Completed']]
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        created = all_todos.filter(created_at__date=day).count()
        done = all_todos.filter(completed=True, updated_at__date=day).count()
        trend_data.append([day.strftime('%b %d'), str(created), str(done)])
    trend_table = Table(trend_data, colWidths=[6*cm, 5*cm, 5*cm])
    trend_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d4a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.HexColor('#f0f7fc'), colors.white]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#ddeaf3')),
        ('ROWHEIGHT', (0, 0), (-1, -1), 22),
    ]))
    elements.append(trend_table)

    elements.append(Spacer(1, 24))
    elements.append(HRFlowable(width="100%", thickness=1,
                               color=colors.HexColor('#a8cce0')))
    elements.append(Spacer(1, 8))
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#6a9bbf'),
        alignment=1
    )
    elements.append(Paragraph(
        f'Taskly Productivity Report · Generated on {today.strftime("%B %d, %Y")} · {user.username}',
        footer_style
    ))

    doc.build(elements)
    return response

@regular_user_required
def shared_tasks(request):
    all_shared = SharedTask.objects.all().order_by('-created_at')

    for task in all_shared:
        SharedTaskCompletion.objects.get_or_create(
            task=task, user=request.user
        )

    tasks_with_status = []
    for task in all_shared:
        completion = SharedTaskCompletion.objects.get(
            task=task, user=request.user
        )
        is_assigned = task.assigned_to.filter(id=request.user.id).exists()
        tasks_with_status.append({
            'task': task,
            'completion': completion,
            'is_assigned': is_assigned,
        })

    form = SharedTaskForm()
    return render(request, 'todos/shared_tasks.html', {
        'tasks_with_status': tasks_with_status,
        'form': form,
    })

@regular_user_required
def create_shared_task(request):
    if request.method == 'POST':
        form = SharedTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            task.save()
            form.save_m2m()
   
            for user in task.assigned_to.all():
                SharedTaskCompletion.objects.get_or_create(
                    task=task, user=user
                )
            messages.success(request, 'Shared task created successfully!')
        else:
            messages.error(request, 'Please fix the errors below.')
    return redirect('shared_tasks')

@regular_user_required
def shared_task_detail(request, pk):
    task = get_object_or_404(SharedTask, pk=pk)
    comments = task.comments.all().order_by('created_at')
    completions = task.completions.all().select_related('user')
    comment_form = SharedTaskCommentForm()

    completion, _ = SharedTaskCompletion.objects.get_or_create(
        task=task, user=request.user
    )
    is_assigned = task.assigned_to.filter(id=request.user.id).exists()

    return render(request, 'todos/shared_task_detail.html', {
        'task': task,
        'comments': comments,
        'completions': completions,
        'comment_form': comment_form,
        'completion': completion,
        'is_assigned': is_assigned,
    })

@regular_user_required
def toggle_shared_task(request, pk):
    task = get_object_or_404(SharedTask, pk=pk)
    completion, _ = SharedTaskCompletion.objects.get_or_create(
        task=task, user=request.user
    )
    completion.completed = not completion.completed
    completion.completed_at = timezone.now() if completion.completed else None
    completion.save()
    messages.success(request, 'Task status updated!')
    return redirect('shared_task_detail', pk=pk)

@regular_user_required
def add_shared_comment(request, pk):
    task = get_object_or_404(SharedTask, pk=pk)
    if request.method == 'POST':
        form = SharedTaskCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.task = task
            comment.user = request.user
            comment.save()
            messages.success(request, 'Comment added!')
    return redirect('shared_task_detail', pk=pk)

@regular_user_required
def delete_shared_task(request, pk):
    task = get_object_or_404(SharedTask, pk=pk, created_by=request.user)
    task.delete()
    messages.success(request, 'Shared task deleted!')
    return redirect('shared_tasks')

@regular_user_required
def shared_task_progress(request):
    tasks = SharedTask.objects.filter(created_by=request.user).order_by('-created_at')
    tasks_progress = []
    for task in tasks:
        completions = task.completions.all().select_related('user')
        tasks_progress.append({
            'task': task,
            'completions': completions,
            'rate': task.completion_rate(),
            'done': task.completion_count(),
            'total': task.total_assigned(),
        })
    return render(request, 'todos/shared_task_progress.html', {
        'tasks_progress': tasks_progress,
    })

def shared_task_public(request, pk):
    task = get_object_or_404(SharedTask, pk=pk)
    comments = task.comments.all().order_by('created_at')
    completions = task.completions.all().select_related('user')

    completion = None
    is_assigned = False

    if request.user.is_authenticated and not request.user.is_superuser:
        completion, _ = SharedTaskCompletion.objects.get_or_create(
            task=task, user=request.user
        )
        is_assigned = task.assigned_to.filter(id=request.user.id).exists()

    return render(request, 'todos/shared_task_public.html', {
        'task': task,
        'comments': comments,
        'completions': completions,
        'completion': completion,
        'is_assigned': is_assigned,
        'comment_form': SharedTaskCommentForm() if request.user.is_authenticated else None,
    })

def search_users(request):
    query = request.GET.get('q', '')
    users = []
    if query:
        users = User.objects.filter(
            username__icontains=query,
            is_superuser=False,
            is_staff=False
        ).exclude(id=request.user.id).values('id', 'username')[:10]
    return JsonResponse({'users': list(users)})

@regular_user_required
def create_shared_task(request):
    if request.method == 'POST':
        form = SharedTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            task.save()

            assigned_ids = request.POST.get('assigned_user_ids', '')
            if assigned_ids:
                for uid in assigned_ids.split(','):
                    uid = uid.strip()
                    if uid:
                        try:
                            user = User.objects.get(id=int(uid))
                            task.assigned_to.add(user)
                            SharedTaskCompletion.objects.get_or_create(
                                task=task, user=user
                            )
                        except (User.DoesNotExist, ValueError):
                            pass

            messages.success(request, 'Shared task created successfully!')
        else:
            messages.error(request, 'Please fix the errors.')
    return redirect('shared_tasks')