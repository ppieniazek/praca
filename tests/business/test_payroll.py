from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from business.models import Payroll, Project, Worker, WorkLog
from core.models import Organization, User


@pytest.mark.django_db
class TestPayrollLogic:
    def get_test_data(self):
        org = Organization.objects.create(name="Test Org")
        owner = User.objects.create_user(
            username="owner", password="pwd", role=User.Role.OWNER, organization=org
        )
        worker = Worker.objects.create(
            organization=org, first_name="Jan", last_name="Kowalski", hourly_rate=20
        )
        project = Project.objects.create(organization=org, name="A", is_default=True)
        return org, owner, worker, project

    def test_payroll_generation(self, client):
        org, owner, worker, project = self.get_test_data()
        client.force_login(owner)

        # Utwórz WorkLog na poprzedni miesiąc
        last_month = timezone.now().replace(day=1) - timedelta(days=15)
        WorkLog.objects.create(
            organization=org,
            worker=worker,
            date=last_month,
            hours=8,
            project=project,
            created_by=owner,
        )

        url = (
            reverse("business:payroll_generate")
            + f"?year={last_month.year}&month={last_month.month}"
        )
        response = client.post(url, headers={"datastar-request": "true"})
        assert response.status_code == 200

        payroll = Payroll.objects.filter(
            worker=worker, year=last_month.year, month=last_month.month
        ).first()
        assert payroll is not None
        assert payroll.status == Payroll.Status.DRAFT
        assert payroll.total_hours == 8
        assert payroll.hourly_rate_snapshot == 20
        assert payroll.gross_pay == Decimal("160.00")

    def test_payroll_close(self, client):
        org, owner, worker, project = self.get_test_data()
        client.force_login(owner)
        last_month = timezone.now().replace(day=1) - timedelta(days=15)
        payroll = Payroll.objects.create(
            organization=org,
            worker=worker,
            year=last_month.year,
            month=last_month.month,
            status=Payroll.Status.DRAFT,
            total_hours=10,
            hourly_rate_snapshot=20,
            gross_pay=200,
            net_pay=200,
            advances_deducted=0,
        )
        url = (
            reverse("business:payroll_close")
            + f"?year={last_month.year}&month={last_month.month}"
        )
        client.post(url, headers={"datastar-request": "true"})

        payroll.refresh_from_db()
        assert payroll.status == Payroll.Status.CLOSED

    def test_payroll_reopen(self, client):
        org, owner, worker, project = self.get_test_data()
        client.force_login(owner)
        last_month = timezone.now().replace(day=1) - timedelta(days=15)
        payroll = Payroll.objects.create(
            organization=org,
            worker=worker,
            year=last_month.year,
            month=last_month.month,
            status=Payroll.Status.CLOSED,
            total_hours=10,
            hourly_rate_snapshot=20,
            gross_pay=200,
            net_pay=200,
            advances_deducted=0,
        )
        url = (
            reverse("business:payroll_reopen")
            + f"?year={last_month.year}&month={last_month.month}"
        )
        client.post(url, headers={"datastar-request": "true"})

        payroll.refresh_from_db()
        assert payroll.status == Payroll.Status.DRAFT
