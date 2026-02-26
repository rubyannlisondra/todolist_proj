from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('add/', views.add_todo, name='add_todo'),
    path('edit/<int:pk>/', views.edit_todo, name='edit_todo'),
    path('toggle/<int:pk>/', views.toggle_todo, name='toggle_todo'),
    path('delete/<int:pk>/', views.delete_todo, name='delete_todo'),
    path('archive/<int:pk>/', views.archive_todo, name='archive_todo'),
    path('archived/', views.archived_tasks, name='archived_tasks'),
    path('deleted/', views.deleted_tasks, name='deleted_tasks'),
    path('restore/<int:pk>/', views.restore_todo, name='restore_todo'),
    path('permanent-delete/<int:pk>/', views.permanent_delete, name='permanent_delete'),
    path('add-category/', views.add_category, name='add_category'),
    path('subtask/add/<int:pk>/', views.add_subtask, name='add_subtask'),
    path('subtask/toggle/<int:pk>/', views.toggle_subtask, name='toggle_subtask'),
    path('subtask/delete/<int:pk>/', views.delete_subtask, name='delete_subtask'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('history/', views.task_history, name='task_history'),
    path('delete-category/<int:pk>/', views.delete_category, name='delete_category'),
]