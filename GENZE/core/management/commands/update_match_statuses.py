from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from django.core.mail import send_mail
from django.conf import settings
from core.models import Match, Reminder
import pytz

class Command(BaseCommand):
    help = "Automatically update match statuses and send reminder emails"

    def handle(self, *args, **options):
        grace_period = timedelta(minutes=15)

        # 1. Upcoming → Live
        upcoming_to_live = Match.objects.filter(status='upcoming')
        for match in upcoming_to_live:
            tz_name = match.tournament.timezone or 'Asia/Kolkata'
            try:
                tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                tz = pytz.timezone('Asia/Kolkata')

            match_time_local = match.match_time.astimezone(tz)
            now_local = timezone.now().astimezone(tz)

            if match_time_local <= now_local:
                match.status = 'live'
                match.live_started_at = timezone.now()
                match.save(update_fields=['status', 'live_started_at'])
                self.stdout.write(self.style.SUCCESS(
                    f"[UPCOMING→LIVE] {match.team1.name} vs {match.team2.name} ({tz_name})"
                ))

        # 2. Live → Completed
        live_to_completed = Match.objects.filter(
            status='live',
            team1_score__isnull=False,
            team2_score__isnull=False
        ).filter(
            Q(youtube_live_url__isnull=True) |
            Q(youtube_live_url='') |
            Q(match_time__lt=timezone.now() - grace_period)
        )

        for match in live_to_completed:
            match.status = 'completed'
            match.completed_at = timezone.now()
            match.save(update_fields=['status', 'completed_at'])
            self.stdout.write(self.style.SUCCESS(
                f"[LIVE→COMPLETED] {match.team1.name} vs {match.team2.name}"
            ))

        # 3. Send reminder emails at match-time minus notify_minutes_before
        now = timezone.now()
        reminders_to_send = Reminder.objects.filter(sent=False).select_related('match', 'match__tournament')

        for reminder in reminders_to_send:
            send_time = reminder.match.match_time - timedelta(minutes=reminder.notify_minutes_before)
            if send_time <= now:
                try:
                    send_mail(
                        subject=f"Upcoming Match: {reminder.match.team1.name} vs {reminder.match.team2.name}",
                        message=(
                            f"Hello,\n\n"
                            f"This is your reminder for the upcoming match:\n"
                            f"Tournament: {reminder.match.tournament.title}\n"
                            f"Stage: {reminder.match.stage or '—'}\n"
                            f"Match Time: {reminder.match.match_time.strftime('%b %d, %Y %I:%M %p')}\n\n"
                            f"Watch Live: {reminder.match.youtube_live_url or 'Link will be available when live'}\n\n"
                            f"GENZE ESPORTS"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[reminder.email],
                        fail_silently=False,
                    )
                    reminder.sent = True
                    reminder.save(update_fields=['sent'])
                    self.stdout.write(self.style.SUCCESS(
                        f"[REMINDER SENT] {reminder.email} for {reminder.match}"
                    ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f"[REMINDER FAILED] {reminder.email} for {reminder.match} — {e}"
                    ))

        self.stdout.write(self.style.NOTICE("Match status update + reminder check complete."))