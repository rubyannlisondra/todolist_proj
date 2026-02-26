from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):
    name = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Todo(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    RECURRENCE_CHOICES = [
        ('none', 'None'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateField(null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    recurrence = models.CharField(max_length=10, choices=RECURRENCE_CHOICES, default='none')
    is_archived = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title

    def subtask_count(self):
        return self.subtasks.count()

    def completed_subtask_count(self):
        return self.subtasks.filter(completed=True).count()

    def subtask_progress(self):
        total = self.subtasks.count()
        if total == 0:
            return 0
        return int((self.subtasks.filter(completed=True).count() / total) * 100)

class Subtask(models.Model):
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name='subtasks')
    title = models.CharField(max_length=200)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class TodoHistory(models.Model):
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name='history')
    changed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    change_description = models.CharField(max_length=255)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.todo.title} - {self.change_description}'

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(blank=True)
    profile_picture_url = models.URLField(blank=True)
    dark_mode = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username