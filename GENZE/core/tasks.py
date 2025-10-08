# core/tasks.py
from celery import shared_task
from django.core.management import call_command

@shared_task
def update_match_statuses_task():
    # Calls the management command we wrote earlier
    call_command('update_match_statuses')