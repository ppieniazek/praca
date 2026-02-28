from datetime import timedelta

import pytest
from django.utils import timezone

from business.models import Vacation, Worker
from core.models import Organization, User


@pytest.mark.django_db
class TestVacationViews:
    def get_test_data(self):
        org = Organization.objects.create(name="Test Org")
        owner = User.objects.create_user(
            username="owner", password="pwd", role=User.Role.OWNER, organization=org
        )
        worker = Worker.objects.create(
            organization=org, first_name="Jan", last_name="Kowalski", hourly_rate=20
        )
        return org, owner, worker

    def test_vacation_create_view(self, client):
        org, owner, worker = self.get_test_data()
        client.force_login(owner)
        from django.urls import reverse

        now = timezone.now().date()
        url = reverse("business:vacation_create", args=[worker.pk])
        response = client.post(
            url,
            {
                "start_date": now.isoformat(),
                "end_date": (now + timedelta(days=2)).isoformat(),
                "description": "Wypoczynek",
            },
            headers={"datastar-request": "true"},
        )
        assert response.status_code == 200
        assert Vacation.objects.filter(worker=worker).count() == 1

    def test_vacation_delete_view(self, client):
        org, owner, worker = self.get_test_data()
        client.force_login(owner)
        from django.urls import reverse

        vacation = Vacation.objects.create(
            organization=org,
            worker=worker,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=1),
        )

        url = reverse("business:vacation_delete", args=[vacation.pk])
        response = client.post(url, headers={"datastar-request": "true"})
        assert response.status_code == 200
        assert Vacation.objects.filter(worker=worker).count() == 0
