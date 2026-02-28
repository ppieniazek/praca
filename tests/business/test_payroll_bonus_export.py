import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse
from business.models import Payroll, Project, Worker, WorkLog, BonusDay
from core.models import Organization, User

@pytest.mark.django_db
class TestPayrollBonusExport:
    def setup_method(self):
        self.org = Organization.objects.create(name="Test Org")
        self.owner = User.objects.create_user(
            username="owner", password="pwd", role=User.Role.OWNER, organization=self.org
        )
        self.worker = Worker.objects.create(
            organization=self.org, first_name="Jan", last_name="Kowalski", hourly_rate=20
        )
        self.project = Project.objects.create(organization=self.org, name="A", is_default=True)
        self.test_date = date(2026, 2, 10)

    def test_bonus_calculation(self, client):
        client.force_login(self.owner)
        
        # WorkLog for Feb 10, 2026
        WorkLog.objects.create(
            organization=self.org,
            worker=self.worker,
            date=self.test_date,
            hours=8,
            project=self.project,
            created_by=self.owner,
        )
        
        # Bonus for Feb 10, 2026
        BonusDay.objects.create(
            organization=self.org,
            date=self.test_date,
            amount=50,
            description="Bonus Day"
        )
        
        url = reverse("business:payroll_generate") + "?year=2026&month=2"
        response = client.post(url, headers={"datastar-request": "true"})
        assert response.status_code == 200
        
        payroll = Payroll.objects.get(worker=self.worker, year=2026, month=2)
        # 8h * 20 PLN = 160 + 50 Bonus = 210
        assert payroll.gross_pay == Decimal("210.00")
        assert payroll.net_pay == Decimal("210.00")

    def test_export_pdf_view(self, client):
        client.force_login(self.owner)
        
        # Create a CLOSED payroll
        Payroll.objects.create(
            organization=self.org,
            worker=self.worker,
            year=2026,
            month=2,
            status=Payroll.Status.CLOSED,
            total_hours=10,
            hourly_rate_snapshot=20,
            gross_pay=200,
            net_pay=200,
            advances_deducted=0,
        )
        
        url = reverse("business:payroll_export_pdf") + "?year=2026&month=2"
        response = client.get(url)
        
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert "attachment" in response["Content-Disposition"]
        assert "wyplaty_02_2026.pdf" in response["Content-Disposition"]

    def test_export_excel_view(self, client):
        client.force_login(self.owner)
        
        # Create a CLOSED payroll
        Payroll.objects.create(
            organization=self.org,
            worker=self.worker,
            year=2026,
            month=2,
            status=Payroll.Status.CLOSED,
            total_hours=10,
            hourly_rate_snapshot=20,
            gross_pay=200,
            net_pay=200,
            advances_deducted=0,
        )
        
        url = reverse("business:payroll_export_excel") + "?year=2026&month=2"
        response = client.get(url)
        
        assert response.status_code == 200
        assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "attachment" in response["Content-Disposition"]
        assert "wyplaty_02_2026.xlsx" in response["Content-Disposition"]

    def test_export_not_found_if_not_closed(self, client):
        client.force_login(self.owner)
        
        # Create a DRAFT payroll
        Payroll.objects.create(
            organization=self.org,
            worker=self.worker,
            year=2026,
            month=2,
            status=Payroll.Status.DRAFT,
            total_hours=10,
            hourly_rate_snapshot=20,
            gross_pay=200,
            net_pay=200,
            advances_deducted=0,
        )
        
        url = reverse("business:payroll_export_pdf") + "?year=2026&month=2"
        response = client.get(url)
        assert response.status_code == 404

    def test_bonus_day_manage_closed_month(self, client):
        client.force_login(self.owner)
        
        # Create a CLOSED payroll for Feb 2026
        Payroll.objects.create(
            organization=self.org,
            worker=self.worker,
            year=2026,
            month=2,
            status=Payroll.Status.CLOSED,
            total_hours=10,
            hourly_rate_snapshot=20,
            gross_pay=200,
            net_pay=200,
            advances_deducted=0,
        )
        
        url = reverse("business:bonus_day_manage") + "?year=2026&month=2"
        response = client.post(url, {"action": "add", "date": "2026-02-15", "amount": 100})
        
        # Check if error message is present in response (Datastar SSE)
        assert response.status_code == 200
        content = b"".join(response.streaming_content).decode().replace("\ndata: elements ", "")
        assert "Nie można edytować bonusów w zamkniętym miesiącu" in content
        assert not BonusDay.objects.filter(date="2026-02-15").exists()
