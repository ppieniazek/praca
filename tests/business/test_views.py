import pytest
from django.urls import reverse
from asgiref.sync import sync_to_async
from business.models import Worker
from core.models import Organization, User
from django.utils import timezone

@pytest.mark.django_db
class TestWorkerViews:
    async def test_worker_list_view_requires_login(self, async_client):
        url = reverse("business:worker_list")
        response = await async_client.get(url)
        assert response.status_code == 302
        assert reverse("core:login") in response.url

    async def test_worker_list_view_redirect_for_foreman(self, async_client):
        org = await Organization.objects.acreate(name="Foreman Corp")
        foreman = await sync_to_async(User.objects.create_user)(username="foreman1", password="pass", organization=org, role=User.Role.FOREMAN)
        
        await sync_to_async(async_client.force_login)(foreman)
        url = reverse("business:worker_list")
        response = await async_client.get(url)
        # Now redirects to dashboard
        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")

    async def test_worker_list_view_isolation(self, async_client):
        org1 = await Organization.objects.acreate(name="Firma A")
        org2 = await Organization.objects.acreate(name="Firma B")
        
        user1 = await sync_to_async(User.objects.create_user)(username="szef1", password="pass", organization=org1, role=User.Role.OWNER)
        
        await Worker.objects.acreate(organization=org1, first_name="Jan", last_name="A-Org1", hourly_rate=30)
        await Worker.objects.acreate(organization=org2, first_name="Piotr", last_name="B-Org2", hourly_rate=35)
        
        await sync_to_async(async_client.force_login)(user1)
        url = reverse("business:worker_list")
        response = await async_client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        assert "Jan" in content
        assert "A-Org1" in content
        assert "Piotr" not in content
        assert "B-Org2" not in content

    async def test_worker_list_search_datastar(self, async_client):
        org = await Organization.objects.acreate(name="Search Corp")
        user = await sync_to_async(User.objects.create_user)(username="searcher", password="pass", organization=org, role=User.Role.OWNER)
        
        await Worker.objects.acreate(organization=org, first_name="Target", last_name="Hit", hourly_rate=10)
        await Worker.objects.acreate(organization=org, first_name="Miss", last_name="Other", hourly_rate=10)
        
        await sync_to_async(async_client.force_login)(user)
        url = reverse("business:worker_list")
        
        # Test 1: Szukamy "Target" (with Datastar header)
        # AsyncClient headers arg needs lowercase keys usually or try meta
        response = await async_client.get(f"{url}?search=Target", headers={"datastar-request": "true"})
        assert response.status_code == 200
        
        if hasattr(response, 'streaming_content'):
            if hasattr(response.streaming_content, '__aiter__'):
                chunks = [chunk async for chunk in response.streaming_content]
            else:
                chunks = list(response.streaming_content)
            streaming_content = b"".join(chunks).decode()
            
            assert "event: datastar-patch-elements" in streaming_content
            assert "Target" in streaming_content
            assert "Miss" not in streaming_content
        else:
            pytest.fail("Response should be streaming (DatastarResponse)")

    async def test_worker_create_modal(self, async_client):
        org = await Organization.objects.acreate(name="Create Corp")
        user = await sync_to_async(User.objects.create_user)(username="creator", password="pass", organization=org, role=User.Role.OWNER)
        await sync_to_async(async_client.force_login)(user)
        
        url = reverse("business:worker_create")
        
        # GET
        response = await async_client.get(url)
        assert response.status_code == 200
    
        # POST (Create)
        data = {
            "first_name": "New",
            "last_name": "Worker",
            "hourly_rate": 50,
            "hired_at": timezone.now().date().isoformat(),
            "phone": "123",
            "address": "",
            "notes": "",
            "is_active": "on"
        }
        
        response = await async_client.post(url, data)
        assert response.status_code == 200
        
        if hasattr(response.streaming_content, '__aiter__'):
            chunks = [chunk async for chunk in response.streaming_content]
        else:
            chunks = list(response.streaming_content)
        streaming_content = b"".join(chunks).decode()
        
        assert 'selector #worker-list-body' in streaming_content
        assert 'is_modal_open":false' in streaming_content or 'is_modal_open": false' in streaming_content
        assert "New Worker" in streaming_content
        
        assert await Worker.objects.filter(first_name="New", last_name="Worker").aexists()

    async def test_worker_promote_demote_flow(self, async_client):
        org = await Organization.objects.acreate(name="Promote Corp")
        szef = await sync_to_async(User.objects.create_user)(username="szef_prom", password="pass", organization=org, role=User.Role.OWNER)
        worker = await Worker.objects.acreate(organization=org, first_name="Kandydat", last_name="NaSzefa", hourly_rate=40)
        
        await sync_to_async(async_client.force_login)(szef)
        
        promote_url = reverse("business:worker_promote", kwargs={"pk": worker.pk})
        
        # POST Promote
        data = {
            "username": "brygadzista1",
            "password": "temporary_password"
        }
        
        response = await async_client.post(promote_url, data)
        assert response.status_code == 200
        
        # Weryfikacja awansu
        await worker.arefresh_from_db()
        assert worker.user_id is not None
        
        new_user = await User.objects.aget(pk=worker.user_id)
        assert new_user.username == "brygadzista1"
        assert new_user.role == User.Role.FOREMAN
        
        # Demote
        demote_url = reverse("business:worker_demote", kwargs={"pk": worker.pk})
        response = await async_client.post(demote_url)
        assert response.status_code == 200
        
        # Weryfikacja degradacji
        await worker.arefresh_from_db()
        assert worker.user_id is None
        assert not await User.objects.filter(username="brygadzista1").aexists()

    async def test_worker_delete_permanent(self, async_client):
        org = await Organization.objects.acreate(name="Delete Corp")
        szef = await sync_to_async(User.objects.create_user)(username="szef_del", password="pass", organization=org, role=User.Role.OWNER)
        await sync_to_async(async_client.force_login)(szef)
        
        # Test 1: Usuwanie zwykłego pracownika
        worker = await Worker.objects.acreate(organization=org, first_name="DoUsuniecia", last_name="Test", hourly_rate=40)
        url = reverse("business:worker_delete", kwargs={"pk": worker.pk})
        response = await async_client.post(url)
        assert response.status_code == 200
        assert not await Worker.objects.filter(pk=worker.pk).aexists()

        # Test 2: Usuwanie brygadzisty (powinien usunąć też usera)
        foreman_user = await sync_to_async(User.objects.create_user)(username="bryg_to_del", password="pass", organization=org)
        worker2 = await Worker.objects.acreate(organization=org, first_name="Bryg", last_name="DoDel", hourly_rate=40, user=foreman_user)
        
        url2 = reverse("business:worker_delete", kwargs={"pk": worker2.pk})
        response2 = await async_client.post(url2)
        assert response2.status_code == 200
        assert not await Worker.objects.filter(pk=worker2.pk).aexists()
        assert not await User.objects.filter(username="bryg_to_del").aexists()

    async def test_worker_password_reset(self, async_client):
        org = await Organization.objects.acreate(name="Reset Corp")
        szef = await sync_to_async(User.objects.create_user)(username="szef_res", password="pass", organization=org, role=User.Role.OWNER)
        foreman_user = await sync_to_async(User.objects.create_user)(username="bryg1", password="old_pass", organization=org, role=User.Role.FOREMAN)
        worker = await Worker.objects.acreate(organization=org, first_name="Jan", last_name="Reset", hourly_rate=30, user=foreman_user)
        
        await sync_to_async(async_client.force_login)(szef)
        
        url = reverse("business:worker_password_reset", kwargs={"pk": worker.pk})
        
        # POST Reset
        data = {"password": "new_very_secure_password"}
        response = await async_client.post(url, data)
        assert response.status_code == 200
        
        # Verify
        await foreman_user.arefresh_from_db()
        assert foreman_user.check_password("new_very_secure_password")
        assert foreman_user.must_change_password is True
