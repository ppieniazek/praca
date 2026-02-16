import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.mark.django_db
class TestPasswordChangeMiddleware:
    def test_middleware_redirects_if_must_change_password(self, client):
        # Create user with must_change_password=True
        user = User.objects.create_user(username="testuser", password="password", must_change_password=True)
        client.force_login(user)
        
        # Access dashboard -> redirect to password change
        response = client.get(reverse("core:dashboard"))
        assert response.status_code == 302
        assert response.url == reverse("core:password_change")
        
        # Access password change -> 200 OK
        response = client.get(reverse("core:password_change"))
        assert response.status_code == 200
        
        # Access logout -> 302 (allowed)
        response = client.post(reverse("core:logout"))
        assert response.status_code == 302

    def test_middleware_no_redirect_if_false(self, client):
        user = User.objects.create_user(username="testuser2", password="password", must_change_password=False)
        client.force_login(user)
        
        response = client.get(reverse("core:dashboard"))
        assert response.status_code == 200
