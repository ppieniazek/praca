import json

import pytest
from django.urls import reverse
from django.utils import timezone

from business.models import Worker
from core.models import Organization, User


@pytest.mark.django_db
class TestWorkerViews:
    """Testy widoków zarządzania pracownikami."""

    def test_worker_list_view_requires_login(self, client):
        url = reverse("business:worker_list")
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("core:login") in response.url

    def test_worker_list_view_redirect_for_foreman(self, client):
        org = Organization.objects.create(name="Foreman Corp")
        foreman = User.objects.create_user(
            username="foreman1",
            password="pass",
            organization=org,
            role=User.Role.FOREMAN,
        )

        client.force_login(foreman)
        url = reverse("business:worker_list")
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")

    def test_worker_list_view_isolation(self, client):
        org1 = Organization.objects.create(name="Firma A")
        org2 = Organization.objects.create(name="Firma B")

        user1 = User.objects.create_user(
            username="szef1", password="pass", organization=org1, role=User.Role.OWNER
        )

        Worker.objects.create(
            organization=org1, first_name="Jan", last_name="A-Org1", hourly_rate=30
        )
        Worker.objects.create(
            organization=org2, first_name="Piotr", last_name="B-Org2", hourly_rate=35
        )

        client.force_login(user1)
        url = reverse("business:worker_list")
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        assert "Jan" in content
        assert "A-Org1" in content
        assert "Piotr" not in content
        assert "B-Org2" not in content

    def test_worker_list_search_datastar(self, client):
        org = Organization.objects.create(name="Search Corp")
        user = User.objects.create_user(
            username="searcher", password="pass", organization=org, role=User.Role.OWNER
        )

        Worker.objects.create(
            organization=org, first_name="Target", last_name="Hit", hourly_rate=10
        )
        Worker.objects.create(
            organization=org, first_name="Miss", last_name="Other", hourly_rate=10
        )

        client.force_login(user)
        url = reverse("business:worker_list")

        response = client.get(
            url,
            data={"datastar": json.dumps({"search": "Target"})},
            headers={"datastar-request": "true"},
        )
        assert response.status_code == 200

        if hasattr(response, "streaming_content"):
            streaming_content = b"".join(list(response.streaming_content)).decode()
            assert "event: datastar-patch-elements" in streaming_content
            assert "Target" in streaming_content
            assert "Miss" not in streaming_content
        else:
            pytest.fail("Response should be streaming")

    def test_worker_create_modal(self, client):
        org = Organization.objects.create(name="Create Corp")
        user = User.objects.create_user(
            username="creator", password="pass", organization=org, role=User.Role.OWNER
        )
        client.force_login(user)

        url = reverse("business:worker_create")

        response = client.get(url)
        assert response.status_code == 200

        data = {
            "first_name": "New",
            "last_name": "Worker",
            "hourly_rate": 50,
            "hired_at": timezone.now().date().isoformat(),
            "phone": "123",
            "address": "",
            "notes": "",
            "is_active": "on",
        }

        response = client.post(url, data)
        assert response.status_code == 200

        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert "selector #worker-list-body" in streaming_content
        assert (
            'is_modal_open":false' in streaming_content
            or 'is_modal_open": false' in streaming_content
        )
        assert "New Worker" in streaming_content

        assert Worker.objects.filter(first_name="New", last_name="Worker").exists()

    def test_worker_promote_demote_flow(self, client):
        org = Organization.objects.create(name="Promote Corp")
        szef = User.objects.create_user(
            username="szef_prom",
            password="pass",
            organization=org,
            role=User.Role.OWNER,
        )
        worker = Worker.objects.create(
            organization=org, first_name="Kandydat", last_name="NaSzefa", hourly_rate=40
        )

        client.force_login(szef)

        promote_url = reverse("business:worker_promote", kwargs={"pk": worker.pk})
        data = {"username": "brygadzista1", "password": "Temporary123"}

        response = client.post(promote_url, data)
        assert response.status_code == 200

        worker.refresh_from_db()
        assert worker.user_id is not None

        new_user = User.objects.get(pk=worker.user_id)
        assert new_user.username == "brygadzista1"
        assert new_user.role == User.Role.FOREMAN

        demote_url = reverse("business:worker_demote", kwargs={"pk": worker.pk})
        response = client.post(demote_url)
        assert response.status_code == 200

        worker.refresh_from_db()
        assert worker.user_id is None
        assert not User.objects.filter(username="brygadzista1").exists()

    def test_worker_delete_permanent(self, client):
        org = Organization.objects.create(name="Delete Corp")
        szef = User.objects.create_user(
            username="szef_del", password="pass", organization=org, role=User.Role.OWNER
        )
        client.force_login(szef)

        worker = Worker.objects.create(
            organization=org, first_name="DoUsuniecia", last_name="Test", hourly_rate=40
        )
        url = reverse("business:worker_delete", kwargs={"pk": worker.pk})
        response = client.post(url)
        assert response.status_code == 200
        assert not Worker.objects.filter(pk=worker.pk).exists()

        foreman_user = User.objects.create_user(
            username="bryg_to_del", password="pass", organization=org
        )
        worker2 = Worker.objects.create(
            organization=org,
            first_name="Bryg",
            last_name="DoDel",
            hourly_rate=40,
            user=foreman_user,
        )

        url2 = reverse("business:worker_delete", kwargs={"pk": worker2.pk})
        response2 = client.post(url2)
        assert response2.status_code == 200
        assert not Worker.objects.filter(pk=worker2.pk).exists()
        assert not User.objects.filter(username="bryg_to_del").exists()

    def test_worker_password_reset(self, client):
        org = Organization.objects.create(name="Reset Corp")
        szef = User.objects.create_user(
            username="szef_res", password="pass", organization=org, role=User.Role.OWNER
        )
        foreman_user = User.objects.create_user(
            username="bryg1",
            password="old_pass",
            organization=org,
            role=User.Role.FOREMAN,
        )
        worker = Worker.objects.create(
            organization=org,
            first_name="Jan",
            last_name="Reset",
            hourly_rate=30,
            user=foreman_user,
        )

        client.force_login(szef)

        url = reverse("business:worker_password_reset", kwargs={"pk": worker.pk})
        data = {"password": "New_very_secure123"}
        response = client.post(url, data)
        assert response.status_code == 200

        foreman_user.refresh_from_db()
        assert foreman_user.check_password("New_very_secure123")
        assert foreman_user.must_change_password is True

    def test_foreman_cannot_edit_other_foreman(self, client):
        """Sprawdza, czy brygadzista nie może edytować czasu pracy innego brygadzisty."""
        org = Organization.objects.create(name="Test Org")
        f1_user = User.objects.create_user(
            username="f1", password="pw", organization=org, role=User.Role.FOREMAN
        )
        f2_user = User.objects.create_user(
            username="f2", password="pw", organization=org, role=User.Role.FOREMAN
        )
        f2_worker = Worker.objects.create(
            organization=org,
            user=f2_user,
            first_name="F2",
            last_name="F2",
            hourly_rate=100,
        )

        client.force_login(f1_user)

        today = timezone.now().date()
        key = f"log_{today.year}_{today.month}_{f2_worker.id}_{today.day}"
        signals = {key: "8"}

        response = client.get(
            "/czas-pracy/aktualizuj/",
            {"key": key, "datastar": json.dumps(signals)},
            headers={"Datastar-Request": "true"},
        )
        assert response.status_code == 403
