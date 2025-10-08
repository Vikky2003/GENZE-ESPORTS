from django.db import models
from django.utils import timezone
from django.conf import settings


class Game(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Tournament(models.Model):
    STATUS_CHOICES = [
        ('registration', 'Registration Open'),
        ('live', 'Live'),
        ('completed', 'Completed'),
        ('upcoming', 'Upcoming'),
    ]

    title = models.CharField(max_length=255)
    game = models.ForeignKey(Game, on_delete=models.CASCADE,null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    prize_pool = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    teams = models.PositiveIntegerField(null=True, blank=True)  # participants count (admin-editable)
    start_date = models.DateField()
    end_date = models.DateField()
    location = models.CharField(max_length=255, blank=True)
    registration_deadline = models.DateField(null=True, blank=True)
    format = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to='tournaments/', blank=True, null=True)
    featured = models.BooleanField(default=False)
    timezone = models.CharField(
        max_length=50,
        default='Asia/Kolkata',  # sensible default for your region
        help_text="Timezone name (IANA format, e.g., 'Asia/Kolkata', 'America/New_York')", null = True
    )


    def __str__(self):
        return self.title

    # Admin list_display helpers (aligned to existing Match fields)
    def start_time(self):
        """Earliest match_time for this tournament."""
        first_match = self.matches.order_by('match_time').first()
        return first_match.match_time if first_match else None
    start_time.short_description = 'Start Time'

    def end_time(self):
        """Latest known time for this tournament (prefer completed_at, fallback to match_time)."""
        last_match = self.matches.order_by('-match_time').first()
        if not last_match:
            return None
        return last_match.completed_at or last_match.match_time
    end_time.short_description = 'End Time'


class Team(models.Model):
    STATUS_CHOICES = [
        ('live', 'Live'),
        ('upcoming', 'Upcoming'),
        ('', 'None'),
    ]
    name = models.CharField(max_length=100)
    game = models.ForeignKey(Game, on_delete=models.CASCADE,related_name='teams',null=True, blank=True)
    region = models.CharField(max_length=50, blank=True, null=True)
    founded = models.PositiveIntegerField(blank=True, null=True)
    banner = models.ImageField(upload_to='team_banners/', blank=True, null=True)
    logo = models.ImageField(upload_to='team_logos/', blank=True, null=True)
    status_indicator = models.CharField(max_length=10, choices=STATUS_CHOICES, blank=True, default='')
    rank = models.PositiveIntegerField(blank=True, null=True)
    tag = models.CharField(max_length=10, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name


class Player(models.Model):
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=50, blank=True, null=True)  
    email = models.EmailField(default="no-email@example.com")
    discord = models.CharField(max_length=100, blank=True)
    team = models.ForeignKey(Team, related_name='players', on_delete=models.CASCADE)
    is_substitute = models.BooleanField(default=False)
    avatar = models.ImageField(upload_to='player_avatars/', blank=True, null=True)
    role = models.CharField(max_length=50, blank=True, null=True)  # retained for compatibility

    def __str__(self):
        return f"{self.name} ({self.team.name})"


class Match(models.Model):
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('live', 'Live'),
        ('completed', 'Completed'),
    ]

    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE, related_name='matches')
    team1 = models.ForeignKey('Team', on_delete=models.CASCADE, related_name='matches_as_team1')
    team2 = models.ForeignKey('Team', on_delete=models.CASCADE, related_name='matches_as_team2')
    match_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')
    stage = models.CharField(max_length=100, blank=True)
    team1_score = models.PositiveIntegerField(blank=True, null=True)
    team2_score = models.PositiveIntegerField(blank=True, null=True)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, null=True, blank=True)
    viewer_count = models.PositiveIntegerField(default=0)
    viewer_label = models.CharField(max_length=20, blank=True, default="")
    youtube_live_url = models.URLField(blank=True)
    youtube_recap_url = models.URLField(blank=True)

    # Admin-editable fields for Results page features
    current_round = models.PositiveIntegerField(blank=True, null=True)   # live: current round
    total_rounds = models.PositiveIntegerField(blank=True, null=True)     # completed: total rounds
    live_started_at = models.DateTimeField(blank=True, null=True)         # when marked live
    completed_at = models.DateTimeField(blank=True, null=True)            # when marked completed
    points_team1 = models.IntegerField(default=0)                         # admin-set points
    points_team2 = models.IntegerField(default=0)                         # admin-set points

    def __str__(self):
        return f"{self.tournament.title} — {self.team1.name} vs {self.team2.name}"

class MatchReminder(models.Model):
    match = models.ForeignKey('Match', on_delete=models.CASCADE, related_name='match_reminders')
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    notify_minutes_before = models.PositiveIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    sent = models.BooleanField(default=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)

class NewsArticle(models.Model):
    STATUS_CHOICES = [
        ('breaking', 'Breaking'),
        ('update', 'Update'),
        ('announcement', 'Announcement'),
    ]

    title = models.CharField(max_length=255)
    date = models.DateField()
    summary = models.TextField(blank=True, null=True)
    content = models.TextField()
    slug = models.SlugField(unique=True, blank=True, null=True)
    featured = models.BooleanField(default=False)
    image = models.ImageField(upload_to='news/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='update')

    def __str__(self):
        return self.title
    
class Reminder(models.Model):
    match = models.ForeignKey('Match', on_delete=models.CASCADE, related_name='reminders')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField()
    notify_minutes_before = models.PositiveIntegerField(default=30)
    sent = models.BooleanField(default=False)  # track if match-time email sent

    def __str__(self):
        return f"Reminder for {self.match} to {self.email}"

class TournamentParticipant(models.Model):
    """
    Stores a team's registration for a specific tournament.
    """
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='participants')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='tournament_entries')
    manager_name = models.CharField(max_length=100)
    manager_email = models.EmailField()
    manager_phone = models.CharField(max_length=20, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tournament', 'team')  # Prevent duplicate registrations

    def __str__(self):
        return f"{self.team.name} in {self.tournament.title}"
