import pytest
from business.models import Worker
from core.models import Organization

@pytest.mark.django_db
class TestWorkerModel:
    def test_worker_creation(self):
        org = Organization.objects.create(name="Firma A")
        worker = Worker.objects.create(
            organization=org,
            first_name="Jan",
            last_name="Kowalski",
            hourly_rate=30
        )
        assert str(worker) == "Jan Kowalski"
        assert worker.is_active is True
        assert worker.organization == org

    def test_worker_ordering(self):
        org = Organization.objects.create(name="Firma A")
        Worker.objects.create(organization=org, first_name="Zofia", last_name="Abacka", hourly_rate=25)
        Worker.objects.create(organization=org, first_name="Adam", last_name="Babacki", hourly_rate=25)
        
        workers = Worker.objects.all()
        assert workers[0].last_name == "Abacka"
        assert workers[1].last_name == "Babacki"
