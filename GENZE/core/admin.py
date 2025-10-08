from django.contrib import admin
from django.utils.html import format_html
from .models import Tournament, Team, Player, Match, NewsArticle, Game, MatchReminder, TournamentParticipant

# Unregister NewsArticle if already registered
try:
    admin.site.unregister(NewsArticle)
except admin.sites.NotRegistered:
    pass

@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'date', 'featured')
    list_filter = ('status', 'featured', 'date')
    search_fields = ('title', 'summary', 'content')
    prepopulated_fields = {'slug': ('title',)}
    ordering = ('-date',)
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'status', 'date', 'featured', 'image')
        }),
        ('Content', {
            'fields': ('summary', 'content')
        }),
    )

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ('title', 'game', 'start_date', 'start_time', 'end_date', 'end_time', 'teams', 'featured')
    list_filter = ('featured', 'game', 'status')
    search_fields = ('title', 'game__name', 'location')

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'tag', 'game', 'region', 'rank')
    search_fields = ('name', 'tag', 'game', 'region')
    fieldsets = (
        (None, {
            'fields': ('name', 'tag', 'game', 'region', 'founded', 'banner', 'logo', 'status_indicator', 'rank', 'description')
        }),
    )

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'team', 'is_substitute')
    list_filter = ('role', 'is_substitute', 'team')
    search_fields = ('name', 'role', 'team__name')

    fieldsets = (
        (None, {
            'fields': ('name', 'role', 'email', 'discord', 'team', 'is_substitute', 'avatar')
        }),
    )

@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        'tournament', 'game', 'team1', 'team2', 'match_time', 'status',
        'stage', 'team1_score', 'team2_score',
        'current_round', 'total_rounds',
        'points_team1', 'points_team2',
        'live_started_at', 'completed_at'
    )
    list_filter = ('status', 'game', 'tournament', 'stage')
    search_fields = ('tournament__title', 'team1__name', 'team2__name')
    readonly_fields = ()
    fieldsets = (
        (None, {
            'fields': (
                'tournament', 'game', 'stage', 'status', 'match_time',
                'team1', 'team2', 'team1_score', 'team2_score',
                'current_round', 'total_rounds',
                'points_team1', 'points_team2',
                'live_started_at', 'completed_at',
                'viewer_count', 'viewer_label',
                'youtube_live_url', 'youtube_recap_url'
            )
        }),
    )

@admin.register(MatchReminder)
class MatchReminderAdmin(admin.ModelAdmin):
    list_display = ('match', 'email', 'phone', 'notify_minutes_before', 'created_at', 'user')
    list_filter = ('notify_minutes_before', 'created_at')
    search_fields = ('email', 'phone', 'user__email')

@admin.register(TournamentParticipant)
class TournamentParticipantAdmin(admin.ModelAdmin):
    list_display = ('tournament', 'team', 'manager_name', 'manager_email', 'manager_phone', 'registered_at')
    list_filter = ('tournament', 'registered_at')
    search_fields = ('team__name', 'manager_name', 'manager_email', 'manager_phone')
    ordering = ('-registered_at',)

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)
