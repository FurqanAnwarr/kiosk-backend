from django.test import TestCase
from django.core.cache import cache
from home.services import ImageUploadService
import base64
import uuid

class TestImageUploadService(TestCase):
    def setUp(self):
        self.kiosk_uuid = str(uuid.uuid4())
        self.image_uuid = str(uuid.uuid4())
        self.test_image_data = b'test_image_data'
        self.encoded_image = base64.b64encode(self.test_image_data).decode('utf-8')

    def tearDown(self):
        cache.clear()

    def test_store_image(self):
        """Test storing an image in cache"""
        result = ImageUploadService.store_image(
            self.kiosk_uuid,
            self.image_uuid,
            self.test_image_data
        )
        self.assertTrue(result)
        
        # Verify image is in cache
        cache_key = f"image_{self.kiosk_uuid}_{self.image_uuid}"
        cached_data = cache.get(cache_key)
        self.assertEqual(cached_data, self.encoded_image)

    def test_get_image(self):
        """Test retrieving an image from cache"""
        # Store image first
        ImageUploadService.store_image(
            self.kiosk_uuid,
            self.image_uuid,
            self.test_image_data
        )

        # Retrieve image
        result = ImageUploadService.get_image(
            self.kiosk_uuid,
            self.image_uuid
        )
        self.assertEqual(result, self.encoded_image)

    def test_get_nonexistent_image(self):
        """Test retrieving a non-existent image"""
        result = ImageUploadService.get_image(
            self.kiosk_uuid,
            self.image_uuid
        )
        self.assertIsNone(result)

    def test_delete_image(self):
        """Test deleting an image from cache"""
        # Store image first
        ImageUploadService.store_image(
            self.kiosk_uuid,
            self.image_uuid,
            self.test_image_data
        )

        # Delete image
        result = ImageUploadService.delete_image(
            self.kiosk_uuid,
            self.image_uuid
        )
        self.assertTrue(result)

        # Verify image is deleted
        result = ImageUploadService.get_image(
            self.kiosk_uuid,
            self.image_uuid
        )
        self.assertIsNone(result)

    def test_cache_timeout(self):
        """Test that images expire after timeout"""
        # Store image with 1 second timeout
        ImageUploadService.store_image(
            self.kiosk_uuid,
            self.image_uuid,
            self.test_image_data,
            timeout=1
        )

        # Wait for expiration
        import time
        time.sleep(2)

        # Verify image is expired
        result = ImageUploadService.get_image(
            self.kiosk_uuid,
            self.image_uuid
        )
        self.assertIsNone(result) 