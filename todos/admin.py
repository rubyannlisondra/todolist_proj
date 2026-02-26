from django.contrib import admin
from .models import Todo, Category, TodoHistory, UserProfile, Subtask

admin.site.register(Todo)
admin.site.register(Category)
admin.site.register(TodoHistory)
admin.site.register(UserProfile)
admin.site.register(Subtask)
