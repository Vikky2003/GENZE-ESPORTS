from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q, F, IntegerField, Case, When, Sum, Subquery, OuterRef, DateTimeField
from django.utils import timezone
from collections import defaultdict
from django.core.paginator import Paginator
from datetime import timedelta, datetime, date
from django.http import JsonResponse, HttpResponseBadRequest
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
from collections import defaultdict
from collections import OrderedDict
from core.models import Match, Reminder
from .models import Tournament, Team, NewsArticle, Match, Player, Game, MatchReminder, TournamentParticipant

def home_page(request):
    featured_tournaments = Tournament.objects.filter(featured=True).order_by('start_date').only(
        'id', 'title', 'game__name', 'status', 'prize_pool', 'teams',
        'location', 'start_date', 'end_date', 'image'
    )

    main_article = NewsArticle.objects.order_by('-date').first()
    other_articles = (
        NewsArticle.objects.exclude(id=main_article.id).order_by('-date')[:6]
        if main_article else NewsArticle.objects.order_by('-date')[:6]
    )

    context = {
        'featured_tournaments': featured_tournaments,
        'main_article': main_article,
        'other_articles': other_articles,
    }
    return render(request, 'core/home.html', context)

def teams_page(request):
    tab = request.GET.get('tab') or 'rankings'
    game_filter = request.GET.get('game')
    highlight_id = request.GET.get('highlight')

    # Base querysets
    teams_qs = Team.objects.all()
    matches_qs = Match.objects.filter(status__in=['completed', 'live', 'upcoming'])
    tournaments_qs = Tournament.objects.all()

    # Apply game filter consistently (filter by game name)
    if game_filter:
        teams_qs = teams_qs.filter(game__name__iexact=game_filter)
        matches_qs = matches_qs.filter(
            Q(team1__game__name__iexact=game_filter) |
            Q(team2__game__name__iexact=game_filter)
        )
        tournaments_qs = tournaments_qs.filter(game__name__iexact=game_filter)

    # Next upcoming match per team (for teams_grid)
    upcoming_match_subquery = Match.objects.filter(
        Q(team1=OuterRef('pk')) | Q(team2=OuterRef('pk')),
        match_time__gte=timezone.now()
    ).order_by('match_time').values('match_time')[:1]

    # Wins/Losses/Played/Championships annotations — matches must have scores
    teams_with_stats = teams_qs.annotate(
        wins=Count('matches_as_team1', filter=Q(matches_as_team1__status='completed') &
                   Q(matches_as_team1__team1_score__isnull=False) &
                   Q(matches_as_team1__team2_score__isnull=False) &
                   Q(matches_as_team1__team1_score__gt=F('matches_as_team1__team2_score')))
             + Count('matches_as_team2', filter=Q(matches_as_team2__status='completed') &
                     Q(matches_as_team2__team1_score__isnull=False) &
                     Q(matches_as_team2__team2_score__isnull=False) &
                     Q(matches_as_team2__team2_score__gt=F('matches_as_team2__team1_score'))),

        losses=Count('matches_as_team1', filter=Q(matches_as_team1__status='completed') &
                     Q(matches_as_team1__team1_score__isnull=False) &
                     Q(matches_as_team1__team2_score__isnull=False) &
                     Q(matches_as_team1__team1_score__lt=F('matches_as_team1__team2_score')))
               + Count('matches_as_team2', filter=Q(matches_as_team2__status='completed') &
                       Q(matches_as_team2__team1_score__isnull=False) &
                       Q(matches_as_team2__team2_score__isnull=False) &
                       Q(matches_as_team2__team2_score__lt=F('matches_as_team2__team1_score'))),

        matches_played=Count('matches_as_team1', filter=Q(matches_as_team1__status='completed') &
                             Q(matches_as_team1__team1_score__isnull=False) &
                             Q(matches_as_team1__team2_score__isnull=False))
                       + Count('matches_as_team2', filter=Q(matches_as_team2__status='completed') &
                               Q(matches_as_team2__team1_score__isnull=False) &
                               Q(matches_as_team2__team2_score__isnull=False)),

        championships=Count('matches_as_team1', filter=Q(matches_as_team1__stage__icontains='final') &
                             Q(matches_as_team1__status='completed') &
                             Q(matches_as_team1__team1_score__isnull=False) &
                             Q(matches_as_team1__team2_score__isnull=False) &
                             Q(matches_as_team1__team1_score__gt=F('matches_as_team1__team2_score')))
                      + Count('matches_as_team2', filter=Q(matches_as_team2__stage__icontains='final') &
                              Q(matches_as_team2__status='completed') &
                              Q(matches_as_team2__team1_score__isnull=False) &
                              Q(matches_as_team2__team2_score__isnull=False) &
                              Q(matches_as_team2__team2_score__gt=F('matches_as_team2__team1_score'))),

        next_match_date=Subquery(upcoming_match_subquery, output_field=DateTimeField())
    ).prefetch_related('players')

    # Rankings queryset
    team_rankings = teams_with_stats.annotate(
        points=F('wins') * 3
    ).order_by('-points', '-wins', 'name')

    # Compute win_rate on the queryset actually used for rendering
    for t in team_rankings:
        t.win_rate = round((t.wins / t.matches_played) * 100, 1) if t.matches_played else 0

    # Points delta over last 24 hours
    since = timezone.now() - timezone.timedelta(days=1)
    recent_matches = Match.objects.filter(
        status='completed',
        match_time__gte=since
    ).values('team1_id', 'team2_id', 'team1_score', 'team2_score')

    recent_wins_map = {}
    for m in recent_matches:
        if m['team1_score'] is not None and m['team2_score'] is not None:
            if m['team1_score'] > m['team2_score'] and m['team1_id']:
                recent_wins_map[m['team1_id']] = recent_wins_map.get(m['team1_id'], 0) + 1
            elif m['team2_score'] > m['team1_score'] and m['team2_id']:
                recent_wins_map[m['team2_id']] = recent_wins_map.get(m['team2_id'], 0) + 1

    for t in team_rankings:
        t.points_delta = recent_wins_map.get(t.id, 0) * 3

    # Top performers
    top_teams = list(team_rankings[:4])
    top_performers = top_teams

    # Tab logic
    if tab == 'all':
        teams_list = team_rankings
    else:
        teams_list = top_teams

    context = {
        'tab': tab,
        'game_filter': game_filter,
        'highlight_id': highlight_id,
        'professional_teams_count': teams_qs.count(),
        'countries_count': teams_qs.exclude(region__isnull=True).exclude(region='').values('region').distinct().count(),
        'matches_played': matches_qs.filter(status='completed').count(),  # global total
        'total_prize_pool': tournaments_qs.aggregate(Sum('prize_pool'))['prize_pool__sum'] or 0,
        'championships_count': tournaments_qs.filter(status='completed').count(),
        'top_teams': top_teams,
        'top_performers': top_performers,
        'teams': teams_list,
        'games': Game.objects.all()
    }

    return render(request, 'core/teams.html', context)

def team_detail(request, team_id):
    team = get_object_or_404(Team.objects.prefetch_related('players'), pk=team_id)

    # Stats
    completed_scored_team1 = team.matches_as_team1.filter(
        status='completed',
        team1_score__isnull=False,
        team2_score__isnull=False
    )
    completed_scored_team2 = team.matches_as_team2.filter(
        status='completed',
        team1_score__isnull=False,
        team2_score__isnull=False
    )

    matches_played = completed_scored_team1.count() + completed_scored_team2.count()
    wins = completed_scored_team1.filter(team1_score__gt=F('team2_score')).count() + \
           completed_scored_team2.filter(team2_score__gt=F('team1_score')).count()
    championships = completed_scored_team1.filter(
        stage__icontains='final',
        team1_score__gt=F('team2_score')
    ).count() + completed_scored_team2.filter(
        stage__icontains='final',
        team2_score__gt=F('team1_score')
    ).count()
    win_rate = round((wins / matches_played) * 100, 1) if matches_played else 0

    # Extra sections
    upcoming_matches = Match.objects.filter(
        status='upcoming'
    ).filter(
        team1=team
    ) | Match.objects.filter(
        status='upcoming',
        team2=team
    )
    upcoming_matches = upcoming_matches.order_by('match_time')[:5]

    recent_results = Match.objects.filter(
        status='completed'
    ).filter(
        team1=team
    ) | Match.objects.filter(
        status='completed',
        team2=team
    )
    recent_results = recent_results.order_by('-completed_at')[:5]

    tournaments = TournamentParticipant.objects.filter(team=team).select_related('tournament')

    return render(request, 'core/team_detail.html', {
        'team': team,
        'matches_played': matches_played,
        'wins': wins,
        'championships': championships,
        'win_rate': win_rate,
        'upcoming_matches': upcoming_matches,
        'recent_results': recent_results,
        'tournaments': tournaments,
    })


def schedule_page(request):
    game = request.GET.get('game') or ''
    region = request.GET.get('region') or ''
    timeframe = request.GET.get('timeframe') or ''
    location = request.GET.get('location') or ''
    now = timezone.now()

    # Base queryset
    qs = Match.objects.select_related('tournament', 'team1', 'team2').order_by('match_time')

    # Filters
    if game:
        qs = qs.filter(
            Q(team1__game__name__iexact=game) |
            Q(team2__game__name__iexact=game) |
            Q(game__name__iexact=game)  # if Match.game is FK to Game
        )

    if region:
        qs = qs.filter(
            Q(team1__region__iexact=region) |
            Q(team2__region__iexact=region)
        )

    if timeframe == 'today':
        today = date.today()
        qs = qs.filter(match_time__date=today)
    elif timeframe == 'week':
        start = date.today()
        end = start + timedelta(days=7)
        qs = qs.filter(match_time__date__gte=start, match_time__date__lte=end)
    elif timeframe == 'month':
        qs = qs.filter(match_time__year=now.year, match_time__month=now.month)

    # Include ALL statuses in main grid
    left_matches = list(qs.order_by('match_time')[:6])

    # Group matches by date
    grouped = OrderedDict()
    for m in left_matches:
        d = m.match_time.date()
        grouped.setdefault(d, []).append(m)
    grouped_matches = [(d, grouped[d]) for d in grouped]

    # Sidebar: upcoming matches
    right_matches_qs = qs.filter(status='upcoming').order_by('match_time')[:5]
    right_matches = list(right_matches_qs)
    for m in right_matches:
        delta = m.match_time - now
        if delta.total_seconds() > 0:
            hours = int(delta.total_seconds() // 3600)
            m.countdown = f"In {hours} hours" if hours >= 1 else "Less than 1 hour"
        else:
            m.countdown = "Starting soon"

    # Regions list
    regions = Team.objects.exclude(region__isnull=True).exclude(region='').values_list('region', flat=True).distinct().order_by('region')

    # Stats for hero section
    matches_today = Match.objects.filter(match_time__date=timezone.now().date()).count()
    matches_week = Match.objects.filter(
        match_time__date__gte=timezone.now().date(),
        match_time__date__lte=timezone.now().date() + timedelta(days=7)
    ).count()
    timezones_count = 12  # static or calculate dynamically if needed

    return render(request, 'core/schedule.html', {
        'grouped_matches': grouped_matches,
        'upcoming_sidebar': right_matches,
        'games': Game.objects.all(),
        'regions': regions,
        'game_filter': game,
        'region_filter': region,
        'timeframe_filter': timeframe,
        'location_filter': location,
        'matches_today': matches_today,
        'matches_week': matches_week,
        'timezones_count': timezones_count,
    })

def calendar_view(request):
    # Get month/year from query params or default to current month/year
    try:
        month = int(request.GET.get('month', timezone.now().month))
        year = int(request.GET.get('year', timezone.now().year))
    except ValueError:
        month = timezone.now().month
        year = timezone.now().year

    # First day of selected month
    start_date = date(year, month, 1)

    # First day of next month
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    # ✅ Show ALL matches for the month (no status filter)
    matches = Match.objects.select_related('tournament', 'team1', 'team2') \
                           .filter(match_time__date__gte=start_date,
                                   match_time__date__lt=end_date) \
                           .order_by('match_time')

    # Group matches by date
    matches_by_day = defaultdict(list)
    for match in matches:
        matches_by_day[match.match_time.date()].append(match)

    # Days in month
    days_in_month = (end_date - start_date).days
    calendar_days = []
    for i in range(days_in_month):
        day = start_date + timedelta(days=i)
        calendar_days.append({
            'date': day,
            'matches': matches_by_day.get(day, [])
        })

    # Previous and next month for navigation
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year

    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year

    return render(request, 'core/calendar.html', {
        'calendar_days': calendar_days,
        'today': timezone.now().date(),
        'month': month,
        'year': year,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
    })

def results_page(request):
    # Keep your existing implementation; ensure completed matches render recap links
    matches = Match.objects.filter(status='completed').select_related('tournament', 'team1', 'team2').order_by('-match_time')[:20]
    return render(request, 'core/results.html', {'recent_results': matches, 'games': Game.objects.all()})

def create_reminder(request):
    if request.method != 'POST':
        return JsonResponse({"ok": False, "error": "Invalid request"}, status=400)

    bulk = request.POST.get('bulk_reminder') == 'true'
    notify_minutes_before = int(request.POST.get('notify_minutes_before', 30))

    # Determine recipient email
    if request.user.is_authenticated:
        email = request.POST.get('email') or request.user.email
    else:
        email = request.POST.get('email')

    if not email:
        return JsonResponse({"ok": False, "error": "Email is required"}, status=400)

    reminders_created = []

    if bulk:
        # Create reminders for all upcoming matches in current filters
        matches = Match.objects.filter(status='upcoming', match_time__gte=timezone.now())
        for match in matches:
            reminder = Reminder.objects.create(
                match=match,
                user=request.user if request.user.is_authenticated else None,
                email=email,
                notify_minutes_before=notify_minutes_before
            )
            reminders_created.append(reminder)

        subject = "Bulk reminders set for upcoming matches"
        message = (
            f"You will be notified {notify_minutes_before} minutes before each upcoming match.\n\n"
            f"Total matches: {len(reminders_created)}\n"
            f"GENZE ESPORTS"
        )

    else:
        # Single match reminder
        match_id = request.POST.get('match_id')
        if not match_id:
            return JsonResponse({"ok": False, "error": "match_id is required"}, status=400)

        match = get_object_or_404(Match, id=match_id)
        reminder = Reminder.objects.create(
            match=match,
            user=request.user if request.user.is_authenticated else None,
            email=email,
            notify_minutes_before=notify_minutes_before
        )
        reminders_created.append(reminder)

        subject = f"Reminder set for {match.team1.name} vs {match.team2.name}"
        message = (
            f"You will be notified {notify_minutes_before} minutes before the match.\n\n"
            f"Tournament: {match.tournament.title}\n"
            f"Match Time: {match.match_time.strftime('%b %d, %Y %I:%M %p')}\n\n"
            f"GENZE ESPORTS"
        )

    # Send confirmation email
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False
        )
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Email sending failed: {e}"})

    return JsonResponse({"ok": True, "message": "Reminder(s) set and email sent"})  
    return JsonResponse({"ok": False, "error": "Invalid request"}, status=400)  

def delete_reminder(request, pk):
    if request.method != 'POST':
        return HttpResponseBadRequest('Invalid method')
    reminder = get_object_or_404(MatchReminder, pk=pk)
    reminder.delete()
    return JsonResponse({'ok': True})

def results_page(request):
    """
    Renders the results page with live matches, recent results, and tournament brackets.
    Supports: ?team=ID, ?game=Name
    """
    team_id = request.GET.get('team')
    game_filter = request.GET.get('game')

    # Live matches
    live_matches = Match.objects.filter(status='live').select_related(
        'tournament', 'team1', 'team2'
    ).order_by('match_time')

    # Recent results (completed matches)
    recent_results = Match.objects.filter(status='completed').select_related(
        'tournament', 'team1', 'team2'
    ).order_by('-match_time')

    # Apply filters
    if game_filter:
        live_matches = live_matches.filter(
            Q(team1__game__iexact=game_filter) | Q(team2__game__iexact=game_filter)
        )
        recent_results = recent_results.filter(
            Q(team1__game__iexact=game_filter) | Q(team2__game__iexact=game_filter)
        )

    if team_id:
        live_matches = live_matches.filter(Q(team1_id=team_id) | Q(team2_id=team_id))
        recent_results = recent_results.filter(Q(team1_id=team_id) | Q(team2_id=team_id))

    # Build brackets list: all tournaments in selected game category (or all if no filter)
    if game_filter:
        tournaments_qs = Tournament.objects.filter(game__name__iexact=game_filter)
    else:
        tournaments_qs = Tournament.objects.all()

    brackets = []
    for t in tournaments_qs:
        upcoming_matches = Match.objects.filter(
            tournament=t,
            status='upcoming'
        ).select_related('team1', 'team2').order_by('match_time')

        if team_id:
            upcoming_matches = upcoming_matches.filter(Q(team1_id=team_id) | Q(team2_id=team_id))

        brackets.append((t, upcoming_matches))

    context = {
        'live_matches': live_matches,
        'recent_results': recent_results,
        'brackets': brackets,
        'games': Game.objects.all(),
        'game_filter': game_filter
    }
    return render(request, 'core/results.html', context)


def team_tournaments(request, team_id):
    team = get_object_or_404(Team, pk=team_id)

    # Only count completed matches with scores present
    completed_scored_team1 = team.matches_as_team1.filter(
        status='completed',
        team1_score__isnull=False,
        team2_score__isnull=False
    )
    completed_scored_team2 = team.matches_as_team2.filter(
        status='completed',
        team1_score__isnull=False,
        team2_score__isnull=False
    )

    matches_played = completed_scored_team1.count() + completed_scored_team2.count()

    matches_won = completed_scored_team1.filter(team1_score__gt=F('team2_score')).count() + \
                  completed_scored_team2.filter(team2_score__gt=F('team1_score')).count()

    win_rate = round((matches_won / matches_played) * 100, 1) if matches_played else 0

    tournaments_played = Tournament.objects.filter(
        Q(matches__team1=team) | Q(matches__team2=team)
    ).distinct().count()

    tournaments_won = Tournament.objects.filter(
        Q(matches__team1=team, matches__stage__icontains='final', matches__team1_score__gt=F('matches__team2_score')) |
        Q(matches__team2=team, matches__stage__icontains='final', matches__team2_score__gt=F('matches__team1_score'))
    ).distinct().count()

    return render(request, 'core/team_tournaments.html', {
        'team': team,
        'matches_played': matches_played,
        'matches_won': matches_won,
        'win_rate': win_rate,
        'tournaments_played': tournaments_played,
        'tournaments_won': tournaments_won,
    })

def register_page(request):
    if request.method == 'POST':
        team_name = request.POST.get('teamName')
        team_tag = request.POST.get('teamTag')
        team_game_id = request.POST.get('teamGame')  # now expecting Game.id
        team_region = request.POST.get('teamRegion')
        team_description = request.POST.get('teamDescription')  # new field
        banner = request.FILES.get('banner')
        logo = request.FILES.get('logo')

        # Validate required fields
        if team_name and team_tag and team_game_id:
            game_obj = get_object_or_404(Game, pk=team_game_id)

            new_team = Team.objects.create(
                name=team_name,
                tag=team_tag,
                game=game_obj,  # store FK instead of string
                region=team_region,
                banner=banner,
                logo=logo,
                description=team_description  # new model field
            )

            # Save up to 5 players with name, role, avatar
            for i in range(1, 6):
                player_name = request.POST.get(f'player_name_{i}')
                player_role = request.POST.get(f'player_role_{i}')
                player_avatar = request.FILES.get(f'player_avatar_{i}')
                if player_name or player_avatar:
                    Player.objects.create(
                        team=new_team,
                        name=player_name or f'Player {i}',
                        role=player_role or '',
                        avatar=player_avatar
                    )

            return redirect(f'/teams/?highlight={new_team.id}&tab=rankings')

    # Open tournaments for Tier 2 registration prompt
    open_tournaments = Tournament.objects.filter(status='registration').only(
        'id', 'title', 'game__name', 'start_date', 'prize_pool', 'location', 'featured', 'image'
    )

    # 🔹 Dynamic values for registration_hero.html
    open_tournaments_count = open_tournaments.count()

    total_prize_pool = open_tournaments.aggregate(
        Sum('prize_pool')
    )['prize_pool__sum'] or 0

    # For now, fixed at 48h — can be made dynamic based on soonest registration_deadline
    registration_deadline_hours = 48

    return render(request, 'core/register.html', {
        'open_tournaments': open_tournaments,
        'games': Game.objects.all(),
        'open_tournaments_count': open_tournaments_count,
        'total_prize_pool': total_prize_pool,
        'registration_deadline_hours': registration_deadline_hours
    })

def tournament_detail_page(request, pk):
    # ✅ Load all fields needed for detail page without extra queries
    tournament = get_object_or_404(
        Tournament.objects.select_related('game').only(
            'id', 'title', 'game__name', 'status', 'prize_pool', 'teams',
            'location', 'start_date', 'end_date', 'image', 'format', 'registration_deadline'
        ),
        pk=pk
    )
    context = {
        'tournament': tournament
    }
    return render(request, 'core/tournament_detail.html', context)


def news_detail(request, pk):
    news_item = get_object_or_404(NewsArticle, pk=pk)
    return render(request, 'core/news_detail.html', {'news_item': news_item})


def news_page(request):
    all_articles = NewsArticle.objects.order_by('-date')
    paginator = Paginator(all_articles, 9)
    page_number = request.GET.get('page')
    news_page_obj = paginator.get_page(page_number)

    return render(request, 'core/news.html', {
        'articles': news_page_obj
    })


def tournaments_page(request):
    """
    Unified tournaments page with filters, sorting, and totals.
    """
    tournaments = Tournament.objects.select_related('game').only(
        'id', 'title', 'game__name', 'status', 'prize_pool', 'teams',
        'location', 'start_date', 'end_date', 'registration_deadline', 'format', 'image'
    )

    # Search
    search_query = request.GET.get('search')
    if search_query:
        tournaments = tournaments.filter(title__icontains=search_query)

    # Filter by game
    game_filter = request.GET.get('game')
    if game_filter:
        tournaments = tournaments.filter(game__name__iexact=game_filter)

    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        tournaments = tournaments.filter(status=status_filter)

    # Sorting
    sort_by = request.GET.get('sort')
    if sort_by == 'prize':
        tournaments = tournaments.order_by('-prize_pool')
    elif sort_by == 'date':
        tournaments = tournaments.order_by('start_date')

    # Totals
    total_prize_pool = tournaments.aggregate(Sum('prize_pool'))['prize_pool__sum'] or 0
    total_participants = sum((t.teams or 0) * 4 for t in tournaments)  # example participants calc
    unique_game_count = tournaments.values('game').distinct().count()

    return render(request, 'core/tournaments.html', {
        'tournaments': tournaments,
        'games': Game.objects.all(),
        'statuses': Tournament.STATUS_CHOICES,
        'total_prize_pool': total_prize_pool,
        'total_participants': total_participants,
        'unique_game_count': unique_game_count
    })

def overall_match_stats(request):
    # 1️⃣ Game/team filters (case-insensitive)
    game_filter = request.GET.get('game')
    team_id = request.GET.get('team')

    teams_qs = Team.objects.all()
    matches_qs = Match.objects.filter(status__in=['completed', 'live', 'upcoming'])
    tournaments_qs = Tournament.objects.all()

    if game_filter:
        teams_qs = teams_qs.filter(game__iexact=game_filter)
        matches_qs = matches_qs.filter(
            Q(team1__game__iexact=game_filter) | Q(team2__game__iexact=game_filter)
        )
        tournaments_qs = tournaments_qs.filter(game__name__iexact=game_filter)

    if team_id:
        teams_qs = teams_qs.filter(id=team_id)
        matches_qs = matches_qs.filter(Q(team1_id=team_id) | Q(team2_id=team_id))

    # 2️⃣ Relax filters in annotations (remove isnull checks, use iexact for status)
    teams_with_stats = teams_qs.annotate(
        wins=Count('matches_as_team1', filter=Q(matches_as_team1__status__iexact='completed') &
                   Q(matches_as_team1__team1_score__gt=F('matches_as_team1__team2_score')))
             + Count('matches_as_team2', filter=Q(matches_as_team2__status__iexact='completed') &
                     Q(matches_as_team2__team2_score__gt=F('matches_as_team2__team1_score'))),

        losses=Count('matches_as_team1', filter=Q(matches_as_team1__status__iexact='completed') &
                     Q(matches_as_team1__team1_score__lt=F('matches_as_team1__team2_score')))
               + Count('matches_as_team2', filter=Q(matches_as_team2__status__iexact='completed') &
                       Q(matches_as_team2__team2_score__lt=F('matches_as_team2__team1_score'))),

        matches_played=Count('matches_as_team1', filter=Q(matches_as_team1__status__iexact='completed'))
                       + Count('matches_as_team2', filter=Q(matches_as_team2__status__iexact='completed')),

        championships=Count('matches_as_team1', filter=Q(matches_as_team1__stage__icontains='final') &
                             Q(matches_as_team1__status__iexact='completed') &
                             Q(matches_as_team1__team1_score__gt=F('matches_as_team1__team2_score')))
                      + Count('matches_as_team2', filter=Q(matches_as_team2__stage__icontains='final') &
                              Q(matches_as_team2__status__iexact='completed') &
                              Q(matches_as_team2__team2_score__gt=F('matches_as_team2__team1_score')))
    )

    # 3️⃣ Rankings + win_rate
    team_rankings = teams_with_stats.annotate(
        points=F('wins') * 3
    ).order_by('-points', '-wins', 'name')

    for t in team_rankings:
        t.win_rate = round((t.wins / t.matches_played) * 100, 1) if t.matches_played else 0

    # 4️⃣ Top performers + chart data
    top_performers = list(team_rankings[:10])
    team_names = [t.name for t in top_performers]
    team_points = [t.points or 0 for t in top_performers]

    # 5️⃣ Fallback chart data if empty
    if not team_names:
        team_names = ['No Data']
        team_points = [0]

    # Global stats
    professional_teams_count = teams_qs.count()
    matches_played_count = matches_qs.filter(status__iexact='completed').count()
    total_prize_pool = tournaments_qs.aggregate(Sum('prize_pool'))['prize_pool__sum'] or 0
    championships_count = tournaments_qs.filter(status__iexact='completed').count()

    # 6️⃣ Tournament stats by game (dynamic for all games)
    tournament_stats_by_game = []
    for game in Game.objects.all():
        game_tournaments = Tournament.objects.filter(game=game)
        stats = {
            'game_name': game.name,
            'active_teams': Team.objects.filter(
                Q(matches_as_team1__tournament__in=game_tournaments) |
                Q(matches_as_team2__tournament__in=game_tournaments)
            ).distinct().count(),
            'matches_played': Match.objects.filter(
                tournament__in=game_tournaments,
                status__iexact='completed'
            ).count(),
            'total_prize_pool': game_tournaments.aggregate(Sum('prize_pool'))['prize_pool__sum'] or 0,
            'championships': game_tournaments.filter(status__iexact='completed').count()
        }
        tournament_stats_by_game.append(stats)

    context = {
        'professional_teams_count': professional_teams_count,
        'matches_played_count': matches_played_count,
        'total_prize_pool': total_prize_pool,
        'championships_count': championships_count,
        'tournament_stats_by_game': tournament_stats_by_game,
        'top_performers': top_performers,
        'top_teams': team_rankings,
        'team_names': team_names,
        'team_points': team_points,
        'games': Game.objects.all(),
        'game_filter': game_filter
    }
    return render(request, 'core/overall_match_stats.html', context)

def tournament_register(request, pk):
    tournament = get_object_or_404(Tournament.objects.select_related('game'), pk=pk)

    team_id = request.GET.get('team_id') or request.POST.get('team_id')
    team = None
    if team_id:
        team = get_object_or_404(Team.objects.prefetch_related('players'), pk=team_id)

    if request.method == 'POST':
        manager_name = request.POST.get('manager_name')
        manager_email = request.POST.get('manager_email')
        manager_phone = request.POST.get('manager_phone')

        if not team:
            messages.error(request, 'Please select a team to register.')
        elif not manager_name or not manager_email:
            messages.error(request, 'Manager name and email are required.')
        else:
            # ✅ Save tournament participant record
            TournamentParticipant.objects.create(
                tournament=tournament,
                team=team,
                manager_name=manager_name,
                manager_email=manager_email,
            )
            messages.success(request, f'{team.name} has been registered for {tournament.title}.')
            return redirect('tournament_detail_page', pk=tournament.id)

    return render(request, 'core/tournament_register.html', {
        'tournament': tournament,
        'tournament': tournament,
        'team': team
    })

