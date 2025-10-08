from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from core.models import MatchReminder

class Command(BaseCommand):
    help = "Send due match reminders to users"

    def handle(self, *args, **options):
        now = timezone.now()

        # Get reminders that haven't been sent yet
        due_reminders = MatchReminder.objects.filter(sent=False)

        for reminder in due_reminders:
            match = reminder.match
            notify_time = match.match_time - timedelta(minutes=reminder.notify_minutes_before)

            # If it's time to send the reminder
            if notify_time <= now:
                body = (
                    f"Reminder: {match.team1.name} vs {match.team2.name}\n"
                    f"Starts at {match.match_time.strftime('%Y-%m-%d %H:%M')} EST\n"
                    f"Tournament: {match.tournament.title}\n"
                    f"Stage: {match.stage}\n"
                    f"Game: {match.game}\n"
                )

                if match.status == 'live' and match.youtube_live_url:
                    body += f"\nWatch Live: {match.youtube_live_url}"
                elif match.status == 'completed' and match.youtube_recap_url:
                    body += f"\nView Recap: {match.youtube_recap_url}"

                if reminder.email:
                    try:
                        send_mail(
                            subject=f"Match Reminder: {match.team1.name} vs {match.team2.name}",
                            message=body,
                            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                            recipient_list=[reminder.email],
                            fail_silently=False
                        )
                        self.stdout.write(self.style.SUCCESS(
                            f"Sent reminder {reminder.id} to {reminder.email}"
                        ))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(
                            f"Failed to send reminder {reminder.id} to {reminder.email}: {e}"
                        ))

                # Mark as sent
                reminder.sent = True
                reminder.save()