from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from datetime import date, timedelta
from .models import Todo, Category, TodoHistory, UserProfile, Subtask
from .forms import TodoForm, CategoryForm, UserProfileForm, UserUpdateForm, SubtaskForm
from functools import wraps

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
    # Redirect already logged in regular users
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
    # Redirect already logged in regular users
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
            # Block superusers/staff from logging in here
            if user.is_superuser or user.is_staff:
                #messages.error(request, 'Admin accounts must log in via /admin/.')
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

# ─── Todo Views ───────────────────────────────────────────────────────
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