from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.home_page, name='home'),
    path('tournaments/', views.tournaments_page, name='tournaments'),
    path('teams/', views.teams_page, name='teams'),
    path('schedule/', views.schedule_page, name='schedule'),
    path('results/', views.results_page, name='results'),
    path('register/', views.register_page, name='register'),
    path('tournaments/<int:pk>/', views.tournament_detail_page, name='tournament_detail'),
    path('news/<int:pk>/', views.news_detail, name='news_detail'),
    path('news/', views.news_page, name='news'),
    path('schedule/', views.schedule_page, name='schedule'),
    path('results/', views.results_page, name='results'),
    path('create-reminder/', views.create_reminder, name='create_reminder'),
    path('delete-reminder/<int:pk>/', views.delete_reminder, name='delete_reminder'),
    path('teams/<int:team_id>/', views.team_detail, name='team_detail'),
    path('teams/<int:team_id>/tournaments/', views.team_tournaments, name='team_tournaments'),
    path('calendar/', views.calendar_view, name='calendar_view'),
    path('match-stats/', views.overall_match_stats, name='overall_match_stats'),
    path('tournaments/<int:pk>/register/', views.tournament_register, name='tournament_register'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
