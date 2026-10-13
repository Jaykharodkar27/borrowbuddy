from datetime import timedelta

from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from borrowing.models import BorrowRequest


class Command(BaseCommand):
    help = "Send due-soon and overdue reminders for borrowed items."

    def handle(self, *args, **options):
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        active = BorrowRequest.objects.filter(
            status=BorrowRequest.Status.COLLECTED
        ).select_related("item", "item__owner", "borrower")

        sent = 0
        for r in active:
            if r.end_date == tomorrow:
                sent += self._send(
                    r.borrower,
                    f"Reminder: return '{r.item.title}' tomorrow",
                    f"Hi {r.borrower.username},\n\nPlease return '{r.item.title}' to "
                    f"{r.item.owner.username} by {r.end_date}.\n\nThanks,\nBorrowBuddy",
                )
            elif r.end_date < today:
                days = (today - r.end_date).days
                sent += self._send(
                    r.borrower,
                    f"Overdue: '{r.item.title}'",
                    f"Hi {r.borrower.username},\n\n'{r.item.title}' was due on {r.end_date} "
                    f"and is {days} day(s) overdue. Please return it to "
                    f"{r.item.owner.username}.\n\nThanks,\nBorrowBuddy",
                )
                sent += self._send(
                    r.item.owner,
                    f"Overdue: '{r.item.title}' has not been returned",
                    f"Hi {r.item.owner.username},\n\n{r.borrower.username} has not returned "
                    f"'{r.item.title}' (due {r.end_date}, {days} day(s) overdue).\n\n"
                    f"BorrowBuddy",
                )

        self.stdout.write(self.style.SUCCESS(f"Sent {sent} reminder(s)."))

    def _send(self, user, subject, message):
        if not user.email:
            return 0
        send_mail(subject, message, None, [user.email])
        return 1