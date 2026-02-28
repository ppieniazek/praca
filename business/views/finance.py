from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.django import DatastarResponse
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Sum, Q, F, DecimalField
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from business.forms import AdvanceForm, ExpenseForm, RefillForm
from business.models import Wallet, WalletTransaction, Worker
from business.views.utils import (
    get_toast_event,
    get_user_org,
    render_template,
)

User = get_user_model()


def get_annotated_finances(organization, queryset=None):
    if queryset is None:
        queryset = Wallet.objects.filter(organization=organization)

    today = timezone.now()
    return queryset.annotate(
        total_refills=Coalesce(
            Sum("transactions__amount", filter=Q(transactions__type="REFILL")),
            0,
            output_field=DecimalField(),
        ),
        total_expenses=Coalesce(
            Sum("transactions__amount", filter=Q(transactions__type="EXPENSE")),
            0,
            output_field=DecimalField(),
        ),
        total_advances=Coalesce(
            Sum("transactions__amount", filter=Q(transactions__type="ADVANCE")),
            0,
            output_field=DecimalField(),
        ),
        monthly_expenses_sum=Coalesce(
            Sum(
                "transactions__amount",
                filter=Q(
                    transactions__type="EXPENSE",
                    transactions__date__year=today.year,
                    transactions__date__month=today.month,
                ),
            ),
            0,
            output_field=DecimalField(),
        ),
    ).annotate(current_balance=F("total_refills") - F("total_expenses") - F("total_advances"))


def get_or_create_finance(request):
    organization = get_user_org(request.user)
    wallet, _ = Wallet.objects.get_or_create(
        user=request.user, organization=organization
    )
    return wallet


def refresh_finance_content(request, wallet=None):
    organization = get_user_org(request.user)

    if wallet:
        wallet = get_annotated_finances(organization).get(pk=wallet.pk)
        transactions = wallet.transactions.all().order_by("-date", "-id")[:30]

        context = {
            "wallet": wallet,
            "transactions": transactions,
            "current_balance": wallet.current_balance,
            "monthly_expenses_sum": wallet.monthly_expenses_sum,
            "total_advances_sum": wallet.total_advances,
        }

        rendered_wallet = render_template(
            "business/finance_detail.html#finance_content", context, request
        )

        return [
            SSE.patch_elements(
                rendered_wallet, selector="#finance-content", mode="inner"
            ),
            get_toast_event(request),
        ]
    else:
        wallets = get_annotated_finances(
            organization,
            Wallet.objects.filter(
                organization=organization, user__role=User.Role.FOREMAN
            ).select_related("user"),
        )

        recent_transactions = WalletTransaction.objects.filter(
            organization=organization
        ).order_by("-date", "-id")[:15]

        total_balance = wallets.aggregate(total=Sum("current_balance"))["total"] or 0

        rendered_list = render_template(
            "business/finance_list.html#finance_list_dashboard",
            {
                "wallets": wallets,
                "total_balance": total_balance,
                "recent_transactions": recent_transactions,
            },
            request,
        )
        return [
            SSE.patch_elements(
                rendered_list, selector="#finance-list-dashboard", mode="inner"
            ),
            get_toast_event(request),
        ]


def finance_list_view(request: HttpRequest):
    if not request.user.is_authenticated:
        return redirect("core:login")

    if request.user.is_owner:
        organization = get_user_org(request.user)

        foremen_without_wallet = User.objects.filter(
            organization=organization, role=User.Role.FOREMAN, wallet__isnull=True
        )
        if foremen_without_wallet.exists():
            Wallet.objects.bulk_create(
                [
                    Wallet(user=foreman, organization=organization)
                    for foreman in foremen_without_wallet
                ]
            )

        wallets = get_annotated_finances(
            organization,
            Wallet.objects.filter(
                organization=organization, user__role=User.Role.FOREMAN
            ).select_related("user"),
        )

        recent_transactions = WalletTransaction.objects.filter(
            organization=organization
        ).order_by("-date", "-id")[:15]

        total_balance = wallets.aggregate(total=Sum("current_balance"))["total"] or 0

        from business.views.project import get_projects

        projects = get_projects(organization)

        context = {
            "wallets": wallets,
            "total_balance": total_balance,
            "recent_transactions": recent_transactions,
            "projects": projects,
        }
        return HttpResponse(
            render_template("business/finance_list.html", context, request)
        )

    wallet = get_or_create_finance(request)
    return redirect("business:finance_detail", pk=wallet.pk)


def finance_detail_view(request: HttpRequest, pk: int):
    if not request.user.is_authenticated:
        return redirect("core:login")

    organization = get_user_org(request.user)
    try:
        wallet = get_annotated_finances(organization).get(pk=pk)
    except Wallet.DoesNotExist:
        messages.error(request, "Portfel nie istnieje.")
        return redirect("business:finance_list")

    if not request.user.is_owner and wallet.user != request.user:
        messages.error(request, "Brak uprawnień do tego portfela.")
        return redirect("business:finance_list")

    if "Datastar-Request" in request.headers:
        return DatastarResponse(refresh_finance_content(request, wallet))

    transactions = wallet.transactions.all().order_by("-date", "-id")[:30]

    context = {
        "wallet": wallet,
        "transactions": transactions,
        "current_balance": wallet.current_balance,
        "monthly_expenses_sum": wallet.monthly_expenses_sum,
        "total_advances_sum": wallet.total_advances,
    }

    content = render_template("business/finance_detail.html", context, request)
    return HttpResponse(content)


def refill_create_view(request: HttpRequest):
    if not request.user.is_authenticated or not request.user.is_owner:
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    wallet_id = request.GET.get("wallet_id") or request.POST.get("wallet_id")

    try:
        wallet = Wallet.objects.get(id=wallet_id, organization=organization)
    except (Wallet.DoesNotExist, ValueError, TypeError):
        messages.error(request, "Nieprawidłowy portfel.")
        return DatastarResponse(get_toast_event(request))

    if request.method == "POST":
        form = RefillForm(request.POST, request.FILES)
        if form.is_valid():
            refill = form.save(commit=False)
            refill.wallet = wallet
            refill.organization = organization
            refill.save()

            messages.success(request, f"Zasilono portfel użytkownika {wallet.user}.")

            if request.GET.get("from_list") == "true":
                events = refresh_finance_content(request, wallet=None)
                events.append(SSE.patch_signals({"is_modal_open": False}))
                return DatastarResponse(events)

            events = refresh_finance_content(request, wallet)
            events.append(SSE.patch_signals({"is_modal_open": False}))
            return DatastarResponse(events)
    else:
        form = RefillForm()

    rendered_modal = render_template(
        "business/finance_list.html#refill_form",
        {
            "form": form,
            "title": f"Zasil portfel: {wallet.user}",
            "url": request.get_full_path(),
        },
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def expense_create_view(request: HttpRequest):
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)

    if request.user.is_owner:
        wallet = None
    else:
        wallet = get_or_create_finance(request)

    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.wallet = wallet
            expense.organization = organization
            expense.save()

            messages.success(request, "Wydatek został zarejestrowany.")

            if request.GET.get("from_list") == "true":
                events = refresh_finance_content(request, wallet=None)
                events.append(SSE.patch_signals({"is_modal_open": False}))
                return DatastarResponse(events)

            events = refresh_finance_content(request, wallet)
            events.append(SSE.patch_signals({"is_modal_open": False}))
            return DatastarResponse(events)
    else:
        form = ExpenseForm()

    rendered_modal = render_template(
        "business/finance_detail.html#expense_form",
        {
            "form": form,
            "title": "Dodaj wydatek" if wallet else "Dodaj wydatek firmowy",
            "url": request.get_full_path(),
        },
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def advance_create_view(request: HttpRequest):
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)

    if request.user.is_owner:
        wallet = None
    else:
        wallet = get_or_create_finance(request)

    worker_id = request.GET.get("worker_id") or request.POST.get("worker_id")

    worker = None
    if worker_id:
        try:
            worker = Worker.objects.get(id=worker_id, organization=organization)
        except (Worker.DoesNotExist, ValueError, TypeError):
            pass

    if request.method == "POST":
        form = AdvanceForm(request.POST, request.FILES, organization=organization)
        if form.is_valid():
            advance = form.save(commit=False)
            advance.wallet = wallet
            advance.organization = organization
            advance.save()

            messages.success(request, "Zaliczka została zarejestrowana.")

            if request.GET.get("from_workers") == "true":
                from business.views.worker import refresh_worker_list

                events = [
                    refresh_worker_list(request, organization),
                    SSE.patch_signals({"is_modal_open": False}),
                    get_toast_event(request),
                ]
                return DatastarResponse(events)

            if request.GET.get("from_list") == "true":
                events = refresh_finance_content(request, wallet=None)
                events.append(SSE.patch_signals({"is_modal_open": False}))
                return DatastarResponse(events)

            events = refresh_finance_content(request, wallet)
            events.append(SSE.patch_signals({"is_modal_open": False}))
            return DatastarResponse(events)
    else:
        initial = {}
        if worker:
            initial["worker"] = worker
        form = AdvanceForm(initial=initial, organization=organization)

    rendered_modal = render_template(
        "business/finance_detail.html#advance_form",
        {
            "form": form,
            "title": f"Zaliczka: {worker}"
            if worker
            else ("Wypłać zaliczkę" if wallet else "Wypłać zaliczkę firmową"),
            "url": request.get_full_path(),
        },
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def transaction_receipt_view(request: HttpRequest, pk: int):
    if not request.user.is_authenticated:
        return HttpResponse(status=403)

    organization = get_user_org(request.user)
    transaction = get_object_or_404(WalletTransaction, pk=pk, organization=organization)

    can_view = request.user.is_owner or (
        transaction.wallet and transaction.wallet.user == request.user
    )

    if not can_view or not transaction.receipt_image:
        return HttpResponse(status=403)

    return FileResponse(transaction.receipt_image.open())


def transaction_receipt_modal(request: HttpRequest, pk: int):
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    transaction = get_object_or_404(WalletTransaction, pk=pk, organization=organization)

    can_view = request.user.is_owner or (
        transaction.wallet and transaction.wallet.user == request.user
    )

    if not can_view or not transaction.receipt_image:
        return DatastarResponse(get_toast_event(request))

    rendered_modal = render_template(
        "business/finance_detail.html#receipt_preview",
        {"transaction": transaction},
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def transaction_edit_view(request: HttpRequest, pk: int):
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    transaction = get_object_or_404(WalletTransaction, pk=pk, organization=organization)

    if not request.user.is_owner and (
        not transaction.wallet or transaction.wallet.user != request.user
    ):
        messages.error(request, "Brak uprawnień do edycji tej transakcji.")
        return DatastarResponse(get_toast_event(request))

    form_class = ExpenseForm
    template_hash = "#expense_form"
    title = "Edytuj wydatek"

    if transaction.type == WalletTransaction.Type.ADVANCE:
        form_class = AdvanceForm
        template_hash = "#advance_form"
        title = "Edytuj zaliczkę"
    elif transaction.type == WalletTransaction.Type.REFILL:
        form_class = RefillForm
        template_hash = "#refill_form"
        title = "Edytuj zasilenie"

    if request.method == "POST":
        form_kwargs = {"instance": transaction}
        if transaction.type == WalletTransaction.Type.ADVANCE:
            form_kwargs["organization"] = organization

        form = form_class(request.POST, request.FILES, **form_kwargs)
        if form.is_valid():
            form.save()
            messages.success(request, "Transakcja została zaktualizowana.")

            if request.GET.get("from_list") == "true" or not transaction.wallet:
                events = refresh_finance_content(request, wallet=None)
            else:
                events = refresh_finance_content(request, transaction.wallet)

            events.append(SSE.patch_signals({"is_modal_open": False}))
            return DatastarResponse(events)
    else:
        form_kwargs = {"instance": transaction}
        if transaction.type == WalletTransaction.Type.ADVANCE:
            form_kwargs["organization"] = organization
        form = form_class(**form_kwargs)

    template_name = "business/finance_detail.html"
    if transaction.type == WalletTransaction.Type.REFILL:
        template_name = "business/finance_list.html"

    rendered_modal = render_template(
        f"{template_name}{template_hash}",
        {
            "form": form,
            "title": title,
            "url": request.get_full_path(),
            "transaction": transaction,
        },
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def transaction_delete_view(request: HttpRequest, pk: int):
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    transaction = get_object_or_404(WalletTransaction, pk=pk, organization=organization)

    if not request.user.is_owner and (
        not transaction.wallet or transaction.wallet.user != request.user
    ):
        messages.error(request, "Brak uprawnień do usunięcia tej transakcji.")
        return DatastarResponse(get_toast_event(request))

    wallet = transaction.wallet
    transaction.delete()
    messages.success(request, "Transakcja została usunięta.")

    if request.GET.get("from_list") == "true" or not wallet:
        events = refresh_finance_content(request, wallet=None)
    else:
        events = refresh_finance_content(request, wallet)
    return DatastarResponse(events)
