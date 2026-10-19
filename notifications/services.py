"""
Telling committee members about changes. Called from orders/services.py inside
the transaction that issues each order, so notifications commit or roll back
with it.
"""

from django.utils import timezone

from accounts.models import User
from assignments.models import Assignment

from .models import Notification


def notify_committee(*, committee, order, message, also=()):
    """
    Notify everyone currently on `committee`, plus `also` — the staff whose
    roles this change ended, who are no longer on it but need to know.

    Invariants: each person is notified once per change; only people on the
    committee (or just removed from it) are notified, so the Principal hears
    about a committee only when he is on it; external members have no account
    and are skipped. Returns the number of notifications created.
    """
    recipients = set(
        Assignment.objects.active()
        .filter(committee=committee, faculty__isnull=False)
        .values_list("faculty_id", flat=True)
    )
    recipients |= {person.pk for person in also if isinstance(person, User)}
    Notification.objects.bulk_create(
        Notification(recipient_id=pk, committee=committee, order=order, message=message[:500])
        for pk in sorted(recipients)
    )
    return len(recipients)


def mark_all_read(user):
    """Mark every unread notification of `user` as read. Returns how many."""
    return user.notifications.unread().update(read_at=timezone.now())
