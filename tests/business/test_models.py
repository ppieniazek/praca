import pytest
from django.utils import timezone

from business.models import EmploymentPeriod, Project, Worker, WorkLog
from core.models import Organization, User


@pytest.mark.django_db
class TestWorkerModel:
    """Testy modelu Pracownika."""

    def test_worker_deactivation_preserves_user(self):
        """Sprawdza, czy dezaktywacja pracownika nie usuwa konta użytkownika."""
        org = Organization.objects.create(name="Test Org")
        user = User.objects.create_user(
            username="worker_user", password="password", organization=org
        )
        worker = Worker.objects.create(
            organization=org,
            user=user,
            first_name="John",
            last_name="Doe",
            hourly_rate=100,
            is_active=True,
        )

        log = WorkLog.objects.create(
            organization=org,
            worker=worker,
            date=timezone.now().date(),
            hours=8,
            created_by=user,
        )

        worker.is_active = False
        worker.save()

        worker.refresh_from_db()
        assert worker.is_active is False

        user.refresh_from_db()
        assert user.id is not None
        assert user.is_active is False

        log.refresh_from_db()
        assert log.created_by == user

    def test_worker_hired_at_change_preserves_history(self):
        """Sprawdza, czy zmiana daty zatrudnienia aktualizuje historię bez jej usuwania."""
        org = Organization.objects.create(name="Test Org")
        worker = Worker.objects.create(
            organization=org,
            first_name="Jane",
            last_name="Smith",
            hourly_rate=120,
            hired_at=timezone.now().date(),
        )

        assert worker.employment_periods.count() == 1
        p1 = worker.employment_periods.first()

        p1.end_date = p1.start_date + timezone.timedelta(days=30)
        p1.save()

        p2_start = p1.end_date + timezone.timedelta(days=30)
        EmploymentPeriod.objects.create(
            worker=worker, organization=org, start_date=p2_start
        )

        assert worker.employment_periods.count() == 2

        new_hired_at = worker.hired_at - timezone.timedelta(days=5)
        worker.hired_at = new_hired_at
        worker.save()

        assert worker.employment_periods.count() == 2

        p1.refresh_from_db()
        assert p1.start_date == new_hired_at
