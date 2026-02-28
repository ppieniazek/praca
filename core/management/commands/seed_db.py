import random
import calendar
from datetime import timedelta, date

from django.core.management.base import BaseCommand
from django.utils import timezone

from business.models import (
    EmploymentPeriod,
    Payroll,
    Project,
    Vacation,
    Wallet,
    WalletTransaction,
    Worker,
    WorkLog,
    BonusDay,
)
from core.models import Organization, User


class Command(BaseCommand):
    help = "Seeds the database with initial data for development (Owner + 4 Foremen + 10+ Workers + Finances + 2 months history)"

    def handle(self, *args, **options):
        self.stdout.write("Seeding database...")

        self.stdout.write("Clearing existing data...")
        BonusDay.objects.all().delete()
        Payroll.objects.all().delete()
        Vacation.objects.all().delete()
        WorkLog.objects.all().delete()
        EmploymentPeriod.objects.all().delete()
        WalletTransaction.objects.all().delete()
        Wallet.objects.all().delete()
        Worker.objects.all().delete()
        Project.objects.all().delete()
        User.objects.all().delete()
        Organization.objects.all().delete()

        self.stdout.write("Creating Organization...")
        org = Organization.objects.create(name="PAVER-OS Demo Firm")

        self.stdout.write("Creating Owner user (owner/test)...")
        owner = User.objects.create_user(
            username="owner",
            first_name="Szef",
            last_name="Właściciel",
            password="test",
            role=User.Role.OWNER,
            organization=org,
            is_staff=True,
            is_superuser=True,
        )

        self.stdout.write("Creating Projects...")
        now = timezone.now().date()
        Project.objects.create(
            organization=org,
            name="Ogólny",
            is_default=True,
            status=Project.Status.ACTIVE,
        )
        p1 = Project.objects.create(
            organization=org,
            name="Osiedle Nowa Perspektywa",
            address="ul. Długa 10, Warszawa",
            status=Project.Status.ACTIVE,
            start_date=now - timedelta(days=90),
            end_date=now + timedelta(days=120),
        )
        p2 = Project.objects.create(
            organization=org,
            name="Parking Galeria Północ",
            address="ul. Krótka 5, Kraków",
            status=Project.Status.ACTIVE,
            start_date=now - timedelta(days=60),
            end_date=now + timedelta(days=30),
        )
        p3 = Project.objects.create(
            organization=org,
            name="Przebudowa Rynku",
            address="Rynek Główny, Wrocław",
            status=Project.Status.ACTIVE,
            start_date=now - timedelta(days=30),
            end_date=now + timedelta(days=180),
        )
        projects = [p1, p2, p3]

        self.stdout.write("Creating 4 Foremen and 10+ workers...")
        teams = [
            (
                "foreman1",
                "Marek",
                "Nowak",
                [("Krzysztof", "Wójcik"), ("Piotr", "Kamiński"), ("Adam", "Zieliński")],
            ),
            (
                "foreman2",
                "Piotr",
                "Kowalski",
                [("Tomasz", "Zieliński"), ("Paweł", "Woźniak")],
            ),
            (
                "foreman3",
                "Jan",
                "Wiśniewski",
                [
                    ("Michał", "Lewandowski"),
                    ("Kamil", "Szymański"),
                    ("Dawid", "Kaczmarek"),
                ],
            ),
            (
                "foreman4",
                "Andrzej",
                "Zalewski",
                [("Robert", "Kowalczyk"), ("Łukasz", "Grabowski")],
            ),
        ]

        foremen_users = []
        workers = []

        for f_username, f_first, f_last, f_workers in teams:
            user = User.objects.create_user(
                username=f_username,
                first_name=f_first,
                last_name=f_last,
                password="test",
                role=User.Role.FOREMAN,
                organization=org,
            )
            foremen_users.append(user)

            w = Worker.objects.create(
                organization=org,
                user=user,
                first_name=f_first,
                last_name=f_last,
                hourly_rate=45,
                hired_at=now - timedelta(days=365),
            )
            workers.append(w)

            for w_first, w_last in f_workers:
                nw = Worker.objects.create(
                    organization=org,
                    first_name=w_first,
                    last_name=w_last,
                    hourly_rate=random.choice([30, 35, 40]),
                    hired_at=now - timedelta(days=random.randint(100, 300)),
                )
                workers.append(nw)

        self.stdout.write("Generating data for the past 2 months...")

        months_to_seed = []
        for i in range(1, 3):
            month = now.month - i
            year = now.year
            if month <= 0:
                month += 12
                year -= 1
            months_to_seed.append((year, month))

        # Reverse so we seed the oldest month first
        months_to_seed.reverse()

        for year, month in months_to_seed:
            self.stdout.write(f"  -> Seeding {month:02d}/{year}...")

            _, last_day = calendar.monthrange(year, month)

            # 1. Bonus Days (up to 3 Saturdays)
            saturdays = [
                date(year, month, d)
                for d in range(1, last_day + 1)
                if date(year, month, d).weekday() == 5
            ]
            bonus_dates = saturdays[:3]
            for bd in bonus_dates:
                BonusDay.objects.create(
                    organization=org,
                    date=bd,
                    amount=200,
                    description="Premia weekendowa",
                )

            # 2. Refills for foremen for this month
            wallets = []
            for f_user in foremen_users:
                wallet, _ = Wallet.objects.get_or_create(user=f_user, organization=org)
                wallets.append(wallet)
                WalletTransaction.objects.create(
                    wallet=wallet,
                    organization=org,
                    type=WalletTransaction.Type.REFILL,
                    amount=random.randint(3000, 6000),
                    date=date(year, month, 1),
                    description="Zasilenie miesięczne",
                )

            # 3. WorkLogs, Advances, and Payroll per worker
            for worker in workers:
                total_hours = 0
                worker_bonus = 0

                # generate work logs
                for day in range(1, last_day + 1):
                    d = date(year, month, day)
                    weekday = d.weekday()

                    if total_hours >= 200:
                        break

                    if weekday == 6:  # Sunday
                        continue

                    # Randomly skip some days
                    if random.random() > 0.9:
                        continue

                    # Determine hours
                    if weekday == 5:  # Saturday
                        hours = random.choice([6, 8])
                    else:
                        hours = random.choice([8, 10, 12])

                    if total_hours + hours > 200:
                        hours = 200 - total_hours

                    if hours <= 0:
                        break

                    WorkLog.objects.create(
                        organization=org,
                        worker=worker,
                        date=d,
                        hours=hours,
                        project=random.choice(projects),
                        created_by=owner,
                    )
                    total_hours += hours

                    if d in bonus_dates:
                        worker_bonus += 200

                # 4. Advances
                total_advances = 0
                num_advances = random.randint(0, 2)
                for _ in range(num_advances):
                    adv_amount = random.choice([200, 500, 800, 1000])
                    if total_advances + adv_amount > 2000:
                        continue

                    adv_date = date(year, month, random.randint(1, last_day))
                    wallet = random.choice(wallets)
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        organization=org,
                        worker=worker,
                        type=WalletTransaction.Type.ADVANCE,
                        amount=adv_amount,
                        date=adv_date,
                        description="Zaliczka na poczet wypłaty",
                    )
                    total_advances += adv_amount

                # 5. Expenses for foreman
                if worker.user in foremen_users:
                    f_wallet = Wallet.objects.get(user=worker.user)
                    for _ in range(random.randint(2, 5)):
                        WalletTransaction.objects.create(
                            wallet=f_wallet,
                            organization=org,
                            type=WalletTransaction.Type.EXPENSE,
                            amount=random.randint(100, 800),
                            category=random.choice(
                                [c[0] for c in WalletTransaction.Category.choices]
                            ),
                            date=date(year, month, random.randint(1, last_day)),
                            description="Zakupy firmowe",
                            project=random.choice(projects),
                        )

                # 6. Create Payroll
                gross_pay = (total_hours * worker.hourly_rate) + worker_bonus
                net_pay = gross_pay - total_advances
                Payroll.objects.create(
                    organization=org,
                    worker=worker,
                    year=year,
                    month=month,
                    status=Payroll.Status.CLOSED,
                    total_hours=total_hours,
                    hourly_rate_snapshot=worker.hourly_rate,
                    bonuses=worker_bonus,
                    gross_pay=gross_pay,
                    advances_deducted=total_advances,
                    net_pay=net_pay,
                )

        self.stdout.write(self.style.SUCCESS("Database seeded successfully!"))
        self.stdout.write(
            "Logins: owner/test, foreman1/test, foreman2/test, foreman3/test, foreman4/test"
        )
