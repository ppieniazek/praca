from datastar_py import ServerSentEventGenerator as SSE
from django.template.loader import render_to_string


def get_user_org(user):
    return user.organization


def is_owner(user):
    return user.is_owner


def render_template(template_name, context, request):
    return render_to_string(template_name, context, request=request)


def get_toast_event(request):
    """Generuje zdarzenie SSE dla powiadomień toast."""
    html = render_template("partials.html#toast_messages", {}, request)
    return SSE.patch_elements(html, selector="#toast-container")
