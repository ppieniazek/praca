from django.core.management.base import BaseCommand
from django.utils import timezone

from business.models import EmploymentPeriod, Project, Worker, WorkLog
from core.models import Organization, User


class Command(BaseCommand):
    help = "Seeds the database with initial data for development (Owner + 10 Workers + 2 Foremen)"

    def handle(self, *args, **options):
        self.stdout.write("Seeding database...")

        # 1. Clear existing data
        self.stdout.write("Clearing existing data...")
        WorkLog.objects.all().delete()
        EmploymentPeriod.objects.all().delete()
        Worker.objects.all().delete()
        Project.objects.all().delete()
        User.objects.all().delete()
        Organization.objects.all().delete()

        # 2. Create Organization
        self.stdout.write("Creating Organization...")
        org = Organization.objects.create(name="PAVER-OS Demo Firm")

        # 3. Create Owner user
        self.stdout.write("Creating Owner user (owner/test)...")
        owner = User.objects.create_user(
            username="owner",
            password="test",
            role=User.Role.OWNER,
            organization=org,
            is_staff=True,
            is_superuser=True,
        )

        # 4. Define Workers Data
        # We will create 10 workers in total.
        # Two of them will be promoted to Foreman.
        workers_data = [
            ("Marek", "Nowak", 25, "foreman1"),
            ("Piotr", "Kowalski", 30, "foreman2"),
            ("Anna", "Wiśniewska", 35, None),
            ("Krzysztof", "Wójcik", 40, None),
            ("Katarzyna", "Kowalczyk", 45, None),
            ("Tomasz", "Kamiński", 28, None),
            ("Agnieszka", "Lewandowska", 32, None),
            ("Michał", "Zieliński", 38, None),
            ("Ewa", "Szymańska", 42, None),
            ("Paweł", "Woźniak", 26, None),
        ]

        self.stdout.write("Creating 10 Workers (including 2 foremen)...")
        for first_name, last_name, rate, username in workers_data:
            user = None
            if username:
                self.stdout.write(f"  - Creating Foreman account: {username}/test")
                user = User.objects.create_user(
                    username=username,
                    password="test",
                    role=User.Role.FOREMAN,
                    organization=org,
                )

            Worker.objects.create(
                organization=org,
                user=user,
                first_name=first_name,
                last_name=last_name,
                hourly_rate=rate,
                hired_at=timezone.now().date(),
            )

        # 5. Create Projects
        self.stdout.write("Creating Projects...")
        Project.objects.create(
            organization=org,
            name="Baza / Warsztat",
            client="Wewnętrzny",
            is_base=True,
            status=Project.Status.ACTIVE,
        )
        Project.objects.create(
            organization=org,
            name="Osiedle Słoneczne",
            client="Deweloper S.A.",
            status=Project.Status.ACTIVE,
        )

        self.stdout.write(self.style.SUCCESS("Database seeded successfully!"))
        self.stdout.write("Logins: owner/test, foreman1/test, foreman2/test")
