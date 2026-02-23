import json
import uuid

import pytest
from django.urls import reverse
from django.utils import timezone

from business.models import Worker, WorkLog
from core.models import Organization, User


@pytest.mark.django_db
class TestTimesheetViews:
    """Testy widoków ewidencji czasu pracy."""

    def get_test_data(self):
        uid = uuid.uuid4().hex[:6]
        org = Organization.objects.create(name=f"Test Org {uid}")
        owner = User.objects.create_user(
            username=f"owner_{uid}",
            password="pass",
            organization=org,
            role=User.Role.OWNER,
        )
        worker1 = Worker.objects.create(
            organization=org, first_name="Jan", last_name=f"K_{uid}", hourly_rate=30
        )
        worker2 = Worker.objects.create(
            organization=org, first_name="Piotr", last_name=f"N_{uid}", hourly_rate=40
        )
        return org, owner, worker1, worker2

    def test_timesheet_view_access(self, client):
        org, owner, _, _ = self.get_test_data()
        url = reverse("business:timesheet_grid")

        response = client.get(url)
        assert response.status_code == 302

        client.force_login(owner)
        response = client.get(url)
        assert response.status_code == 200
        assert "Ewidencja Czasu Pracy" in response.content.decode()

    def test_timesheet_grid_partial(self, client):
        org, owner, worker1, worker2 = self.get_test_data()
        client.force_login(owner)

        signals = {
            f"workerVisible_{worker1.id}": True,
            f"workerVisible_{worker2.id}": True,
        }
        url = reverse("business:timesheet_grid_partial")
        response = client.get(
            f"{url}?datastar={json.dumps(signals)}",
            headers={"datastar-request": "true"},
        )
        assert response.status_code == 200

        if hasattr(response, "streaming_content"):
            streaming_content = b"".join(list(response.streaming_content)).decode()
            assert "event: datastar-patch-elements" in streaming_content
            assert "selector #timesheet-container" in streaming_content
            assert worker1.last_name in streaming_content
            assert worker2.last_name in streaming_content
        else:
            pytest.fail("View should return DatastarResponse")

    def test_timesheet_manage_workers_modal(self, client):
        org, owner, _, _ = self.get_test_data()
        client.force_login(owner)

        url = reverse("business:timesheet_manage_workers")
        response = client.get(url, headers={"datastar-request": "true"})
        assert response.status_code == 200

        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert "selector #modal-content" in streaming_content
        assert "is_modal_open" in streaming_content

    def test_timesheet_update_view_creates_log(self, client):
        org, owner, worker, _ = self.get_test_data()
        client.force_login(owner)

        now = timezone.now()
        key = f"log_{now.year}_{now.month}_{worker.id}_{now.day}"
        url = (
            reverse("business:timesheet_update")
            + f"?key={key}&year={now.year}&month={now.month}"
        )
        signals = {key: "8"}

        response = client.post(
            url,
            data=json.dumps(signals),
            content_type="application/json",
            headers={"datastar-request": "true"},
        )
        assert response.status_code == 200

        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert f"selector #cell-{worker.id}-{now.day}" in streaming_content

        log = WorkLog.objects.filter(worker=worker, date__day=now.day).first()
        assert log is not None
        assert log.hours == 8
        assert log.created_by_id == owner.id

    def test_timesheet_update_view_deletes_log_on_zero(self, client):
        org, owner, worker, _ = self.get_test_data()
        client.force_login(owner)

        now = timezone.now()
        WorkLog.objects.create(
            worker=worker, date=now.date(), hours=5, organization=org, created_by=owner
        )

        key = f"log_{now.year}_{now.month}_{worker.id}_{now.day}"
        url = (
            reverse("business:timesheet_update")
            + f"?key={key}&year={now.year}&month={now.month}"
        )

        signals = {key: ""}
        response = client.post(
            url,
            data=json.dumps(signals),
            content_type="application/json",
            headers={"datastar-request": "true"},
        )
        assert response.status_code == 200
        assert not WorkLog.objects.filter(worker=worker, date__day=now.day).exists()

    def test_timesheet_bulk_fill_creates_logs(self, client):
        org, owner, worker1, worker2 = self.get_test_data()
        client.force_login(owner)

        now = timezone.now()
        date_str = f"{now.year}-{now.month:02d}-{now.day:02d}"

        url = f"{reverse('business:timesheet_bulk_fill')}?date={date_str}"
        payload = {
            f"workerVisible_{worker1.id}": True,
            f"workerVisible_{worker2.id}": True,
            f"bulkInput_{now.day}": "8",
        }

        response = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            headers={"datastar-request": "true"},
        )
        assert response.status_code == 200

        assert WorkLog.objects.filter(worker=worker1, date=now.date(), hours=8).exists()
        assert WorkLog.objects.filter(worker=worker2, date=now.date(), hours=8).exists()

    def test_timesheet_bulk_fill_overwrites_hours_and_creates_history(self, client):
        org, owner, worker1, worker2 = self.get_test_data()

        uid = uuid.uuid4().hex[:6]
        foreman = User.objects.create_user(
            username=f"foreman_{uid}",
            password="pass",
            organization=org,
            role=User.Role.FOREMAN,
        )
        client.force_login(foreman)

        now = timezone.now()
        date_str = f"{now.year}-{now.month:02d}-{now.day:02d}"

        WorkLog.objects.create(
            worker=worker1,
            date=now.date(),
            hours=10,
            organization=org,
            created_by=owner,
        )

        url = f"{reverse('business:timesheet_bulk_fill')}?date={date_str}"
        payload = {
            f"workerVisible_{worker1.id}": True,
            f"workerVisible_{worker2.id}": True,
            f"bulkInput_{now.day}": "8",
        }

        response = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            headers={"datastar-request": "true"},
        )

        assert WorkLog.objects.get(worker=worker1, date=now.date()).hours == 8
        assert WorkLog.objects.get(worker=worker2, date=now.date()).hours == 8

        from business.models import TimesheetHistory

        history = TimesheetHistory.objects.filter(
            worker=worker1, date=now.date()
        ).first()
        assert history is not None
        assert history.old_hours == 10
        assert history.new_hours == 8
        assert history.changed_by == foreman

        streaming_content = b"".join(list(response.streaming_content)).decode()
        assert "Nadpisano wpis" in streaming_content
