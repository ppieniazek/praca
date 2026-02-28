import uuid

import pytest
from django.urls import reverse
from django.utils import timezone

from business.models import Wallet, WalletTransaction, Worker
from core.models import Organization, User


@pytest.mark.django_db
class TestFinance:
    def get_test_data(self):
        uid = uuid.uuid4().hex[:6]
        org = Organization.objects.create(name=f"Test Org {uid}")
        user = User.objects.create_user(
            username=f"user_{uid}",
            password="pass",
            organization=org,
            role=User.Role.FOREMAN,
        )
        worker = Worker.objects.create(
            organization=org, first_name="Jan", last_name=f"K_{uid}", hourly_rate=30
        )
        return org, user, worker

    def test_wallet_balance_calculation(self):
        org, user, worker = self.get_test_data()
        wallet = Wallet.objects.create(user=user, organization=org)

        WalletTransaction.objects.create(
            wallet=wallet,
            organization=org,
            type=WalletTransaction.Type.REFILL,
            amount=1000,
        )
        WalletTransaction.objects.create(
            wallet=wallet,
            organization=org,
            type=WalletTransaction.Type.EXPENSE,
            amount=100,
            category=WalletTransaction.Category.FUEL,
        )
        WalletTransaction.objects.create(
            wallet=wallet,
            organization=org,
            type=WalletTransaction.Type.EXPENSE,
            amount=50,
            category=WalletTransaction.Category.OTHER,
        )
        WalletTransaction.objects.create(
            wallet=wallet,
            worker=worker,
            organization=org,
            type=WalletTransaction.Type.ADVANCE,
            amount=200,
        )

        assert wallet.get_current_balance() == 650

    def test_wallet_view_access(self, client):
        org, user, _ = self.get_test_data()
        wallet = Wallet.objects.create(user=user, organization=org)
        WalletTransaction.objects.create(
            wallet=wallet,
            organization=org,
            type=WalletTransaction.Type.REFILL,
            amount=1000,
        )
        WalletTransaction.objects.create(
            wallet=wallet,
            organization=org,
            type=WalletTransaction.Type.EXPENSE,
            amount=50,
            category=WalletTransaction.Category.OTHER,
            description="Kawa",
        )
        url = reverse("business:finance_list")

        response = client.get(url)
        assert response.status_code == 302

        client.force_login(user)
        response = client.get(url, follow=True)
        assert response.status_code == 200

        content = response.content.decode()
        assert "Finanse" in content
        assert "950" in content
        assert "Kawa" in content
        assert "Historia transakcji" in content

    def test_expense_create_sse(self, client):
        org, user, _ = self.get_test_data()
        wallet = Wallet.objects.create(user=user, organization=org)
        client.force_login(user)

        url = reverse("business:expense_create")
        data = {
            "amount": "150.00",
            "category": WalletTransaction.Category.FUEL,
            "date": timezone.now().date().isoformat(),
            "description": "Test expense",
        }

        response = client.post(url, data=data, headers={"datastar-request": "true"})
        assert response.status_code == 200

        assert WalletTransaction.objects.filter(
            wallet=wallet, amount=150, type=WalletTransaction.Type.EXPENSE
        ).exists()

        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert "event: datastar-patch-elements" in streaming_content
        assert "selector #finance-content" in streaming_content
        assert "is_modal_open" in streaming_content
        assert "false" in streaming_content

    def test_advance_create_sse(self, client):
        org, user, worker = self.get_test_data()
        wallet = Wallet.objects.create(user=user, organization=org)
        client.force_login(user)

        url = reverse("business:advance_create")
        data = {
            "worker": worker.id,
            "amount": "300.00",
            "date": timezone.now().date().isoformat(),
            "description": "Test advance",
        }

        response = client.post(url, data=data, headers={"datastar-request": "true"})
        assert response.status_code == 200

        assert WalletTransaction.objects.filter(
            wallet=wallet,
            worker=worker,
            amount=300,
            type=WalletTransaction.Type.ADVANCE,
        ).exists()
        assert worker.get_total_advances() == 300

        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert "event: datastar-patch-elements" in streaming_content
        assert "selector #finance-content" in streaming_content
        assert "is_modal_open" in streaming_content
        assert "false" in streaming_content
