from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from datetime import date, timedelta
from functools import wraps
from .models import (Todo, Category, TodoHistory, UserProfile, Subtask,
                     Group, GroupMember, GroupTask, GroupSubtask,
                     GroupTaskComment, GroupActivity)
from .forms import (TodoForm, CategoryForm, UserProfileForm, UserUpdateForm,
                    SubtaskForm, GroupForm, GroupTaskForm, GroupTaskCommentForm,
                    GroupSubtaskForm)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.units import cm
import json

# ─── Custom Decorator ────────────────────────────────────────────────
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

# ─── Auth Views ───────────────────────────────────────────────────────
def register_view(request):
    if request.user.is_authenticated and not request.user.is_superuser:
        return redirect('index')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
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
                messages.error(request, 'Admin accounts must log in via /admin/.')
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

# ─── Personal Todo Views ──────────────────────────────────────────────
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
                todo=todo, changed_by=request.user,
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
                todo=todo, changed_by=request.user,
                change_description=f'Task "{todo.title}" was edited.'
            )
            messages.success(request, 'Task updated successfully!')
            return redirect('index')
    else:
        form = TodoForm(instance=todo, user=request.user)
    subtasks = todo.subtasks.all()
    subtask_form = SubtaskForm()
    return render(request, 'todos/edit_todo.html', {
        'form': form, 'todo': todo,
        'subtasks': subtasks, 'subtask_form': subtask_form,
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
            user=request.user, title=todo.title,
            category=todo.category, priority=todo.priority,
            recurrence=todo.recurrence, due_date=new_due,
        )
        messages.success(request, f'Recurring task scheduled for {new_due}!')

    status = 'completed' if todo.completed else 'marked as incomplete'
    TodoHistory.objects.create(
        todo=todo, changed_by=request.user,
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
        todo=todo, changed_by=request.user,
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
        'user_form': user_form, 'profile_form': profile_form,
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

# ─── Analytics Views ──────────────────────────────────────────────────
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

    # Streak
    streak = 0
    check_date = today
    while True:
        if all_todos.filter(completed=True, updated_at__date=check_date).exists():
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    # Score
    score = 0
    if total > 0:
        score += completion_rate * 0.5
        score += min(streak * 5, 30)
        score -= min(overdue * 3, 20)
        score = max(0, min(100, round(score)))

    # Daily Trend
    daily_labels, daily_completed, daily_created = [], [], []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        daily_labels.append(day.strftime('%b %d'))
        daily_completed.append(all_todos.filter(completed=True, updated_at__date=day).count())
        daily_created.append(all_todos.filter(created_at__date=day).count())

    # Weekly Trend
    weekly_labels, weekly_completed = [], []
    for i in range(7, -1, -1):
        week_start = today - timedelta(weeks=i, days=today.weekday())
        week_end = week_start + timedelta(days=6)
        weekly_labels.append(f'Wk {week_start.strftime("%b %d")}')
        weekly_completed.append(all_todos.filter(
            completed=True, updated_at__date__range=[week_start, week_end]
        ).count())

    # Category Stats
    categories = Category.objects.filter(user=user)
    category_data = []
    for cat in categories:
        cat_total = active_todos.filter(category=cat).count()
        cat_done = active_todos.filter(category=cat, completed=True).count()
        if cat_total > 0:
            category_data.append({
                'name': cat.name, 'total': cat_total,
                'completed': cat_done,
                'rate': round(cat_done / cat_total * 100, 1)
            })

    # Priority Stats
    priority_data = []
    for priority, label in [('urgent','Urgent'),('high','High'),('medium','Medium'),('low','Low')]:
        count = active_todos.filter(priority=priority).count()
        done = active_todos.filter(priority=priority, completed=True).count()
        priority_data.append({'label': label, 'total': count, 'completed': done})

    return render(request, 'todos/analytics.html', {
        'total': total, 'completed': completed, 'overdue': overdue,
        'pending': pending, 'completion_rate': completion_rate,
        'streak': streak, 'score': score,
        'daily_labels': json.dumps(daily_labels),
        'daily_completed': json.dumps(daily_completed),
        'daily_created': json.dumps(daily_created),
        'weekly_labels': json.dumps(weekly_labels),
        'weekly_completed': json.dumps(weekly_completed),
        'category_data': category_data,
        'priority_data': priority_data,
        'today': today,
    })

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
        score -= min(overdue * 3, 20)
        score = max(0, min(100, round(score)))

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Taskly_Report_{today}.pdf"'
    doc = SimpleDocTemplate(response, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle('Title', parent=styles['Title'],
        fontSize=24, textColor=colors.HexColor('#2d4a5f'), spaceAfter=4, fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'],
        fontSize=11, textColor=colors.HexColor('#6a9bbf'), spaceAfter=20)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor('#2d4a5f'), spaceBefore=16, spaceAfter=8, fontName='Helvetica-Bold')
    normal_style = ParagraphStyle('Normal2', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#444444'), spaceAfter=4)
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#6a9bbf'), alignment=1)

    elements.append(Paragraph('Taskly', title_style))
    elements.append(Paragraph(f'Productivity Report — {today.strftime("%B %d, %Y")}', subtitle_style))
    elements.append(Paragraph(f'Generated for: {user.username}', normal_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#a8cce0'), spaceAfter=16))

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
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2d4a5f')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 11),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f0f7fc'), colors.white]),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#ddeaf3')),
        ('ROWHEIGHT', (0,0), (-1,-1), 28),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 16))

    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#ddeaf3'), spaceAfter=8))
    elements.append(Paragraph('Tasks by Priority', heading_style))
    priority_table_data = [['Priority', 'Total', 'Completed', 'Pending']]
    for priority, label in [('urgent','Urgent'),('high','High'),('medium','Medium'),('low','Low')]:
        p_total = active_todos.filter(priority=priority).count()
        p_done = active_todos.filter(priority=priority, completed=True).count()
        priority_table_data.append([label, str(p_total), str(p_done), str(p_total - p_done)])
    priority_table = Table(priority_table_data, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
    priority_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#6a9bbf')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f0f7fc'), colors.white]),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#ddeaf3')),
        ('ROWHEIGHT', (0,0), (-1,-1), 26),
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
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#6a9bbf')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f0f7fc'), colors.white]),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#ddeaf3')),
            ('ROWHEIGHT', (0,0), (-1,-1), 26),
        ]))
        elements.append(cat_table)
    else:
        elements.append(Paragraph('No categories found.', normal_style))

    elements.append(Spacer(1, 16))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#ddeaf3'), spaceAfter=8))
    elements.append(Paragraph('Daily Trend (Last 14 Days)', heading_style))
    trend_data = [['Date', 'Created', 'Completed']]
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        created = all_todos.filter(created_at__date=day).count()
        done = all_todos.filter(completed=True, updated_at__date=day).count()
        trend_data.append([day.strftime('%b %d'), str(created), str(done)])
    trend_table = Table(trend_data, colWidths=[6*cm, 5*cm, 5*cm])
    trend_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2d4a5f')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f0f7fc'), colors.white]),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#ddeaf3')),
        ('ROWHEIGHT', (0,0), (-1,-1), 22),
    ]))
    elements.append(trend_table)
    elements.append(Spacer(1, 24))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#a8cce0')))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        f'Taskly Productivity Report · Generated on {today.strftime("%B %d, %Y")} · {user.username}',
        footer_style
    ))
    doc.build(elements)
    return response

# ─── Search Views ─────────────────────────────────────────────────────
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

def search_group_users(request):
    group_pk = request.GET.get('group_pk')
    query = request.GET.get('q', '')
    users = []
    if query and group_pk:
        group = get_object_or_404(Group, pk=group_pk)
        member_ids = group.members.values_list('id', flat=True)
        users = User.objects.filter(
            id__in=member_ids,
            username__icontains=query,
            is_superuser=False,
        ).exclude(id=request.user.id).values('id', 'username')[:10]
    return JsonResponse({'users': list(users)})

# ─── Group Views ──────────────────────────────────────────────────────
@regular_user_required
def groups_home(request):
    my_groups = Group.objects.filter(members=request.user).order_by('-created_at')
    form = GroupForm()
    return render(request, 'todos/groups_home.html', {
        'my_groups': my_groups, 'form': form,
    })

@regular_user_required
def create_group(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            group = form.save(commit=False)
            group.created_by = request.user
            group.save()
            GroupMember.objects.create(group=group, user=request.user, role='admin')
            GroupActivity.objects.create(
                group=group, user=request.user,
                message=f'{request.user.username} created the group.'
            )
            messages.success(request, f'Group "{group.name}" created!')
            return redirect('group_detail', pk=group.pk)
    return redirect('groups_home')

@regular_user_required
def group_detail(request, pk):
    group = get_object_or_404(Group, pk=pk)
    member = GroupMember.objects.filter(group=group, user=request.user).first()
    if not member:
        messages.error(request, 'You are not a member of this group.')
        return redirect('groups_home')

    tasks = group.group_tasks.all()
    todo_tasks = tasks.filter(status='todo')
    inprogress_tasks = tasks.filter(status='inprogress')
    done_tasks = tasks.filter(status='done')
    members = GroupMember.objects.filter(group=group).select_related('user')
    activities = group.activities.all()[:10]
    task_form = GroupTaskForm()

    priority_filter = request.GET.get('priority', '')
    assignee_filter = request.GET.get('assignee', '')
    view_mode = request.GET.get('view', 'list')

    if priority_filter:
        todo_tasks = todo_tasks.filter(priority=priority_filter)
        inprogress_tasks = inprogress_tasks.filter(priority=priority_filter)
        done_tasks = done_tasks.filter(priority=priority_filter)

    if assignee_filter:
        todo_tasks = todo_tasks.filter(group_subtasks__assigned_to__id=assignee_filter).distinct()
        inprogress_tasks = inprogress_tasks.filter(group_subtasks__assigned_to__id=assignee_filter).distinct()
        done_tasks = done_tasks.filter(group_subtasks__assigned_to__id=assignee_filter).distinct()

    return render(request, 'todos/group_detail.html', {
        'group': group,
        'member': member,
        'todo_tasks': todo_tasks,
        'inprogress_tasks': inprogress_tasks,
        'done_tasks': done_tasks,
        'members': members,
        'activities': activities,
        'task_form': task_form,
        'priority_filter': priority_filter,
        'assignee_filter': assignee_filter,
        'view_mode': view_mode,
        'all_tasks': tasks,
    })

@regular_user_required
def create_group_task(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if not GroupMember.objects.filter(group=group, user=request.user).exists():
        messages.error(request, 'Not a member.')
        return redirect('groups_home')
    if request.method == 'POST':
        form = GroupTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.group = group
            task.created_by = request.user
            task.save()
            GroupActivity.objects.create(
                group=group, user=request.user,
                message=f'{request.user.username} created task "{task.title}".'
            )
            messages.success(request, 'Task created!')
    return redirect('group_detail', pk=pk)

@regular_user_required
def group_task_detail(request, group_pk, task_pk):
    group = get_object_or_404(Group, pk=group_pk)
    task = get_object_or_404(GroupTask, pk=task_pk, group=group)
    if not GroupMember.objects.filter(group=group, user=request.user).exists():
        messages.error(request, 'Not a member.')
        return redirect('groups_home')
    comments = task.comments.all().order_by('created_at')
    comment_form = GroupTaskCommentForm()
    subtasks = task.group_subtasks.all()
    subtask_form = GroupSubtaskForm()
    members = GroupMember.objects.filter(group=group).select_related('user')
    return render(request, 'todos/group_task_detail.html', {
        'group': group, 'task': task,
        'comments': comments, 'comment_form': comment_form,
        'subtasks': subtasks, 'subtask_form': subtask_form,
        'members': members,
    })

@regular_user_required
def update_task_status(request, group_pk, task_pk):
    group = get_object_or_404(Group, pk=group_pk)
    task = get_object_or_404(GroupTask, pk=task_pk, group=group)
    if not GroupMember.objects.filter(group=group, user=request.user).exists():
        messages.error(request, 'Not a member.')
        return redirect('groups_home')
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['todo', 'inprogress', 'done']:
            task.status = new_status
            task.save()
            GroupActivity.objects.create(
                group=group, user=request.user,
                message=f'{request.user.username} moved "{task.title}" to {task.get_status_display()}.'
            )
    return redirect('group_detail', pk=group_pk)

@regular_user_required
def add_group_comment(request, group_pk, task_pk):
    group = get_object_or_404(Group, pk=group_pk)
    task = get_object_or_404(GroupTask, pk=task_pk, group=group)
    if request.method == 'POST':
        form = GroupTaskCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.task = task
            comment.user = request.user
            comment.save()
            GroupActivity.objects.create(
                group=group, user=request.user,
                message=f'{request.user.username} commented on "{task.title}".'
            )
    return redirect('group_task_detail', group_pk=group_pk, task_pk=task_pk)

@regular_user_required
def delete_group_task(request, group_pk, task_pk):
    group = get_object_or_404(Group, pk=group_pk)
    task = get_object_or_404(GroupTask, pk=task_pk, group=group)
    member = GroupMember.objects.filter(group=group, user=request.user).first()
    if member and (member.role == 'admin' or task.created_by == request.user):
        GroupActivity.objects.create(
            group=group, user=request.user,
            message=f'{request.user.username} deleted task "{task.title}".'
        )
        task.delete()
        messages.success(request, 'Task deleted!')
    return redirect('group_detail', pk=group_pk)

@regular_user_required
def add_group_subtask(request, group_pk, task_pk):
    group = get_object_or_404(Group, pk=group_pk)
    task = get_object_or_404(GroupTask, pk=task_pk, group=group)
    if not GroupMember.objects.filter(group=group, user=request.user).exists():
        messages.error(request, 'Not a member.')
        return redirect('groups_home')
    if request.method == 'POST':
        form = GroupSubtaskForm(request.POST)
        if form.is_valid():
            subtask = form.save(commit=False)
            subtask.task = task
            assigned_id = request.POST.get('assigned_to')
            if assigned_id:
                try:
                    assigned_user = User.objects.get(id=int(assigned_id))
                    if GroupMember.objects.filter(group=group, user=assigned_user).exists():
                        subtask.assigned_to = assigned_user
                except (User.DoesNotExist, ValueError):
                    pass
            subtask.save()
            GroupActivity.objects.create(
                group=group, user=request.user,
                message=f'{request.user.username} added subtask "{subtask.title}" to "{task.title}".'
            )
            messages.success(request, 'Subtask added!')
    return redirect('group_task_detail', group_pk=group_pk, task_pk=task_pk)

@regular_user_required
def update_subtask_status(request, group_pk, task_pk, subtask_pk):
    group = get_object_or_404(Group, pk=group_pk)
    task = get_object_or_404(GroupTask, pk=task_pk, group=group)
    subtask = get_object_or_404(GroupSubtask, pk=subtask_pk, task=task)
    if not GroupMember.objects.filter(group=group, user=request.user).exists():
        messages.error(request, 'Not a member.')
        return redirect('groups_home')
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['todo', 'inprogress', 'done']:
            subtask.status = new_status
            subtask.save()
            all_subtasks = task.group_subtasks.all()
            if all_subtasks.count() > 0:
                if all_subtasks.filter(status='done').count() == all_subtasks.count():
                    task.status = 'done'
                elif all_subtasks.filter(status='inprogress').exists():
                    task.status = 'inprogress'
                task.save()
            GroupActivity.objects.create(
                group=group, user=request.user,
                message=f'{request.user.username} updated subtask "{subtask.title}" to {subtask.get_status_display()}.'
            )
    return redirect('group_task_detail', group_pk=group_pk, task_pk=task_pk)

@regular_user_required
def delete_group_subtask(request, group_pk, task_pk, subtask_pk):
    group = get_object_or_404(Group, pk=group_pk)
    task = get_object_or_404(GroupTask, pk=task_pk, group=group)
    subtask = get_object_or_404(GroupSubtask, pk=subtask_pk, task=task)
    member = GroupMember.objects.filter(group=group, user=request.user).first()
    if member and (member.role == 'admin' or task.created_by == request.user):
        subtask.delete()
        messages.success(request, 'Subtask deleted!')
    return redirect('group_task_detail', group_pk=group_pk, task_pk=task_pk)

@regular_user_required
def join_group(request):
    if request.method == 'POST':
        invite_code = request.POST.get('invite_code', '').strip().upper()
        try:
            group = Group.objects.get(invite_code=invite_code)
            if GroupMember.objects.filter(group=group, user=request.user).exists():
                messages.warning(request, 'You are already a member!')
            else:
                GroupMember.objects.create(group=group, user=request.user, role='member')
                GroupActivity.objects.create(
                    group=group, user=request.user,
                    message=f'{request.user.username} joined the group.'
                )
                messages.success(request, f'Joined "{group.name}" successfully!')
                return redirect('group_detail', pk=group.pk)
        except Group.DoesNotExist:
            messages.error(request, 'Invalid invite code. Please try again.')
    return redirect('groups_home')

@regular_user_required
def leave_group(request, pk):
    group = get_object_or_404(Group, pk=pk)
    member = GroupMember.objects.filter(group=group, user=request.user).first()
    if member:
        if group.created_by == request.user:
            messages.error(request, 'You cannot leave a group you created. Delete it instead.')
        else:
            member.delete()
            GroupActivity.objects.create(
                group=group, user=request.user,
                message=f'{request.user.username} left the group.'
            )
            messages.success(request, f'You left "{group.name}".')
    return redirect('groups_home')

@regular_user_required
def delete_group(request, pk):
    group = get_object_or_404(Group, pk=pk, created_by=request.user)
    group.delete()
    messages.success(request, 'Group deleted.')
    return redirect('groups_home')

@regular_user_required
def remove_member(request, group_pk, user_pk):
    group = get_object_or_404(Group, pk=group_pk)
    member = GroupMember.objects.filter(group=group, user=request.user, role='admin').first()
    if member:
        target = GroupMember.objects.filter(group=group, user__id=user_pk).first()
        if target and target.user != request.user:
            username = target.user.username
            target.delete()
            GroupActivity.objects.create(
                group=group, user=request.user,
                message=f'{request.user.username} removed {username} from the group.'
            )
            messages.success(request, f'{username} removed.')
    return redirect('group_detail', pk=group_pk)