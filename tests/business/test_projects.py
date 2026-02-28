import json

import pytest
from django.urls import reverse

from business.models import Project, WalletTransaction, Worker, WorkLog
from core.models import Organization, User


@pytest.mark.django_db
class TestProjectViews:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.org = Organization.objects.create(name="Firma Testowa")
        self.owner = User.objects.create_user(
            username="owner",
            password="password",
            organization=self.org,
            role=User.Role.OWNER,
        )
        self.foreman = User.objects.create_user(
            username="foreman",
            password="password",
            organization=self.org,
            role=User.Role.FOREMAN,
        )
        self.worker1 = Worker.objects.create(
            organization=self.org,
            first_name="Jan",
            last_name="Kowalski",
            hourly_rate=50,
        )
        self.worker2 = Worker.objects.create(
            organization=self.org, first_name="Adam", last_name="Nowak", hourly_rate=40
        )
        self.project1 = Project.objects.create(
            organization=self.org, name="Projekt A", status="ACTIVE"
        )
        self.project2 = Project.objects.create(
            organization=self.org, name="Projekt B", status="PLANNED"
        )
        self.project3 = Project.objects.create(
            organization=self.org, name="Projekt Default", is_default=True
        )

    def test_project_cost_calculation(self, client):
        from business.models import Wallet

        wallet = Wallet.objects.create(organization=self.org, user=self.foreman)

        # 10 hours * 50 = 500
        WorkLog.objects.create(
            organization=self.org,
            worker=self.worker1,
            project=self.project1,
            date="2026-01-01",
            hours=10,
            created_by=self.owner,
        )
        # 5 hours * 40 = 200
        WorkLog.objects.create(
            organization=self.org,
            worker=self.worker2,
            project=self.project1,
            date="2026-01-01",
            hours=5,
            created_by=self.owner,
        )
        # Expense = 300
        WalletTransaction.objects.create(
            organization=self.org,
            project=self.project1,
            wallet=wallet,
            type="EXPENSE",
            amount=300,
            date="2026-01-01",
        )

        # Total expenses should be 300, total hours 15

        client.force_login(self.owner)
        url = reverse("business:project_detail", kwargs={"pk": self.project1.pk})
        response = client.get(url)

        assert response.status_code == 200
        content = b"".join(response.streaming_content).decode()
        # Check if values are in content (more robust check)
        assert "300" in content
        assert "15" in content

    def test_project_list_access(self, client):
        client.force_login(self.owner)
        url = reverse("business:project_list")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Projekt A" in response.content

    def test_project_list_datastar_search(self, client):
        client.force_login(self.owner)
        url = reverse("business:project_list")
        response = client.get(
            url,
            {"datastar": json.dumps({"search": "Projekt B"})},
            HTTP_DATASTAR_REQUEST="true",
        )
        assert response.status_code == 200
        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert "Projekt A" not in streaming_content
        assert "Projekt B" in streaming_content
        assert response.headers["Content-Type"].startswith("text/event-stream")

    def test_project_create_modal(self, client):
        client.force_login(self.owner)
        url = reverse("business:project_create")
        response = client.get(url)
        assert response.status_code == 200
        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert "Dodaj projekt" in streaming_content
        assert response.headers["Content-Type"].startswith("text/event-stream")

    def test_project_create_post(self, client):
        client.force_login(self.owner)
        url = reverse("business:project_create")
        response = client.post(url, {"name": "Nowy Projekt", "status": "PLANNED"})
        assert response.status_code == 200
        assert Project.objects.filter(name="Nowy Projekt").exists()
        assert response.headers["Content-Type"].startswith("text/event-stream")
        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert "Dodano projekt:" in streaming_content

    def test_project_edit_post(self, client):
        client.force_login(self.owner)
        url = reverse("business:project_edit", kwargs={"pk": self.project1.pk})
        response = client.post(
            url, {"name": "Zmieniony Projekt", "status": "COMPLETED"}
        )
        assert response.status_code == 200
        self.project1.refresh_from_db()
        assert self.project1.name == "Zmieniony Projekt"
        assert self.project1.status == "COMPLETED"

    def test_foreman_cannot_create_project(self, client):
        client.force_login(self.foreman)
        url = reverse("business:project_create")
        response = client.get(url)
        # Should redirect or deny
        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert "Dodaj projekt" not in streaming_content
        # Foreman can view? Yes, wait no, project_create is owner only
        assert "window.location" in streaming_content

    def test_foreman_cannot_edit_project(self, client):
        client.force_login(self.foreman)
        url = reverse("business:project_edit", kwargs={"pk": self.project1.pk})
        response = client.get(url)
        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert "Edytuj projekt" not in streaming_content
