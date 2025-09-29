from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from rest_framework.test import APIClient
from home.models import KioskClient, KioskHealthCheck
import uuid
import base64
import json
from django.core.files.uploadedfile import SimpleUploadedFile

class TestImageUploadViews(TestCase):
    def setUp(self):
        self.client = Client()
        self.api_client = APIClient()
        self.kiosk_uuid = str(uuid.uuid4())
        self.image_uuid = str(uuid.uuid4())
        
        # Create test kiosk client
        self.kiosk = KioskClient.objects.create(
            login_name='test_kiosk'
        )
        self.kiosk.set_password('test_password')
        self.kiosk.save()

        # Create auth credentials
        credentials = base64.b64encode(b'test_kiosk:test_password').decode()
        self.auth_headers = {'HTTP_AUTHORIZATION': f'Basic {credentials}'}

    def tearDown(self):
        cache.clear()

    def test_upload_page_get(self):
        """Test accessing the upload page"""
        url = reverse('upload-page', args=[self.kiosk_uuid, self.image_uuid])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home/upload.html')
        self.assertContains(response, 'Upload Image')

    def test_handle_upload_no_image(self):
        """Test upload endpoint without an image"""
        url = reverse('handle-upload', args=[self.kiosk_uuid, self.image_uuid])
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertEqual(data['error'], 'No image provided')

    def test_handle_upload_success(self):
        """Test successful image upload"""
        url = reverse('handle-upload', args=[self.kiosk_uuid, self.image_uuid])
        
        # Create a test image file
        image_data = b'test_image_content'
        image_file = SimpleUploadedFile(
            'test.jpg',
            image_data,
            content_type='image/jpeg'
        )
        
        response = self.client.post(url, {'image': image_file})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

    def test_image_status_api_unauthorized(self):
        """Test image status API without authentication"""
        url = reverse('image-status', args=[self.kiosk_uuid, self.image_uuid])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 401)

    def test_image_status_api_not_found(self):
        """Test image status API when image doesn't exist"""
        url = reverse('image-status', args=[self.kiosk_uuid, self.image_uuid])
        response = self.client.get(url, **self.auth_headers)
        
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'pending')

    def test_image_status_api_success(self):
        """Test image status API with existing image"""
        url = reverse('image-status', args=[self.kiosk_uuid, self.image_uuid])
        
        # Store test image in cache
        test_image = b'test_image_data'
        encoded_image = base64.b64encode(test_image).decode('utf-8')
        cache.set(f"image_{self.kiosk_uuid}_{self.image_uuid}", encoded_image)
        
        response = self.client.get(url, **self.auth_headers)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'ready')
        self.assertEqual(data['image'], encoded_image)

class TestImageUploadFlowAPI(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Create test kiosk client for authentication
        self.kiosk = KioskClient.objects.create(
            login_name='test_kiosk'
        )
        self.kiosk.set_password('test_password')
        self.kiosk.save()

        # Create auth credentials
        credentials = base64.b64encode(b'test_kiosk:test_password').decode()
        self.auth_headers = {'HTTP_AUTHORIZATION': f'Basic {credentials}'}

    def test_flow_documentation(self):
        """Test the flow documentation endpoint"""
        url = reverse('image-upload-docs')
        response = self.client.get(url, **self.auth_headers)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('message', data) 

class TestKioskHealthCheckView(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Create test kiosk client
        self.kiosk = KioskClient.objects.create(
            login_name='test_kiosk'
        )
        self.kiosk.set_password('test_password')
        self.kiosk.save()

        # Create health check entry
        KioskHealthCheck.objects.create(kiosk=self.kiosk, is_healthy=True, health_message="All systems operational")

        # Create auth credentials
        credentials = base64.b64encode(b'test_kiosk:test_password').decode()
        self.auth_headers = {'HTTP_AUTHORIZATION': f'Basic {credentials}'}

    def test_health_check_authenticated(self):
        """Test health check endpoint when authenticated"""
        response = self.client.get('/api/health/', **self.auth_headers)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['kiosk_id'], str(self.kiosk.id))
        self.assertEqual(data['login_name'], self.kiosk.login_name)
        self.assertTrue(data['is_healthy'])
        self.assertEqual(data['health_message'], "All systems operational")

    def test_health_check_unauthenticated(self):
        """Test health check endpoint without authentication"""
        response = self.client.get('/api/health/')
        
        self.assertEqual(response.status_code, 401)

    def test_health_check_kiosk_inactive(self):
        """Test health check for an inactive kiosk"""
        self.kiosk.is_active = False
        self.kiosk.save()

        response = self.client.get('/api/health/', **self.auth_headers)
        
        self.assertEqual(response.status_code, 401)
  