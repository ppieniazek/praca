from decimal import Decimal

import pytest
from django.urls import reverse

from business.models import Project, Wallet, WalletTransaction, Worker, WorkLog
from core.models import Organization, User


@pytest.mark.django_db
class TestProjectDetailView:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.org = Organization.objects.create(name="Firma Testowa")
        self.owner = User.objects.create_user(
            username="owner",
            password="password",
            organization=self.org,
            role=User.Role.OWNER,
        )
        self.worker = Worker.objects.create(
            organization=self.org,
            first_name="Jan",
            last_name="Kowalski",
            hourly_rate=Decimal("30.00"),
        )
        self.project = Project.objects.create(
            organization=self.org, name="Test Project", status=Project.Status.ACTIVE
        )

        # Add WorkLog
        WorkLog.objects.create(
            organization=self.org,
            worker=self.worker,
            project=self.project,
            date="2024-01-01",
            hours=Decimal("8.5"),
        )

        # Add Expense
        self.wallet = Wallet.objects.create(user=self.owner, organization=self.org)
        WalletTransaction.objects.create(
            wallet=self.wallet,
            organization=self.org,
            project=self.project,
            type=WalletTransaction.Type.EXPENSE,
            amount=Decimal("500.00"),
            category=WalletTransaction.Category.MATERIAL,
            date="2024-01-01",
            description="Cement",
        )

        # Add another transaction (Advance - should not count towards project expense)
        WalletTransaction.objects.create(
            wallet=self.wallet,
            organization=self.org,
            worker=self.worker,
            type=WalletTransaction.Type.ADVANCE,
            amount=Decimal("100.00"),
            date="2024-01-01",
        )

    def test_project_detail_view_success(self, client):
        client.force_login(self.owner)
        url = reverse("business:project_detail", kwargs={"pk": self.project.pk})
        response = client.get(url)

        assert response.status_code == 200
        content = b"".join(response.streaming_content)
        assert b"Test Project" in content
        assert b"8" in content
        assert b"500.00" in content or b"500,00" in content
        assert b"100.00" not in content
