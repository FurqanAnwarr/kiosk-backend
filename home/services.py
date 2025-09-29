from http.cookiejar import debug

import instaloader
import tempfile
import os
import base64
from datetime import datetime
from django.core.cache import cache
from typing import Optional, List, Dict
import logging
import paypalrestsdk
from django.conf import settings
from .models import Order

logger = logging.getLogger(__name__)

class InstagramService:
    def __init__(self):
        self.loader = instaloader.Instaloader(
            download_pictures=True,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            # debug=True
        )
        self.temp_dir = tempfile.mkdtemp()
        self.loader.context._user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

    def authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate with Instagram using the provided username and password.

        :param username: Instagram username
        :param password: Instagram password
        :return: True if authentication succeeds, False otherwise
        """
        try:
            self.loader.login(username, password)
            self.loader.save_session_to_file()
            logger.info("Authentication successful.")
            return True
        except instaloader.exceptions.BadCredentialsException:
            logger.warning("Invalid username or password.")
        except Exception as e:
            logger.error(f"Error during authentication: {str(e)}")
        return False

    def get_profile_posts(self, username: str, limit: int = 10, cache_timeout: int = 3600) -> List[Dict]:
        cache_key = f'instagram_posts_{username}'
        cached_posts = cache.get(cache_key)

        if cached_posts:
            logger.info(f"Returning cached posts for {username}.")
            return cached_posts

        try:
            profile = instaloader.Profile.from_username(self.loader.context, username)
            posts = []

            for post in profile.get_posts():
                if len(posts) >= limit:
                    break

                # Prepare temp file path for image
                temp_filename = f"{post.date_utc.strftime('%Y%m%d_%H%M%S')}_{post.shortcode}"
                temp_path = os.path.join(self.temp_dir, temp_filename)

                # Download image
                try:
                    logger.info(f"Downloading image for post {post.shortcode} to {temp_path}")
                    self.loader.download_pic(temp_path, post.url, post.date_utc)
                    temp_path += '.jpg'
                    if not os.path.exists(temp_path):
                        logger.warning(f"Image file does not exist: {temp_path}")
                        continue
                except Exception as e:
                    logger.error(f"Error downloading image for post {post.shortcode}: {str(e)}")
                    continue

                # Read and encode image in base64
                encoded_image = None
                try:
                    with open(temp_path, 'rb') as img_file:
                        image_data = img_file.read()
                        base64_data = base64.b64encode(image_data).decode('utf-8')
                        encoded_image = f"data:image/jpeg;base64,{base64_data}"
                        logger.info(f"Base64 encoding successful for post {post.shortcode}")
                except Exception as e:
                    logger.error(f"Error encoding image at {temp_path}: {str(e)}")

                post_data = {
                    'shortcode': post.shortcode,
                    'caption': post.caption if post.caption else '',
                    'likes': post.likes,
                    'date': post.date_utc.isoformat(),
                    'image': encoded_image
                }
                posts.append(post_data)

            cache.set(cache_key, posts, cache_timeout)
            return posts
        except instaloader.exceptions.ProfileNotExistsException:
            logger.warning(f"Profile '{username}' does not exist.")
        except instaloader.exceptions.LoginRequiredException:
            logger.warning("Login required to fetch this profile. Please authenticate.")
        except instaloader.exceptions.RateLimitExceeded:
            logger.warning("Rate limit exceeded. Please wait before trying again.")
        except instaloader.exceptions.InstaloaderException as e:
            logger.error(f"An error occurred while fetching the profile: {e}")
        except Exception as e:
            logger.error(f"Error fetching Instagram posts for {username}: {str(e)}")
        return []

    def cleanup(self):
        """Clean up temporary files"""
        try:
            for file in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            os.rmdir(self.temp_dir)
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

class ImageUploadService:
    """Service to handle temporary image storage and retrieval"""
    
    @staticmethod
    def store_image(kiosk_uuid: str, image_uuid: str, image_data: list[str], timeout: int = 300) -> bool:
        """
        Store image in cache with expiration
        :param kiosk_uuid: Kiosk identifier
        :param image_uuid: Image identifier
        :param image_data: Binary image data
        :param timeout: Cache timeout in seconds (default 5 minutes)
        :return: True if stored successfully
        """
        try:
            cache_key = f"image_{kiosk_uuid}_{image_uuid}"
            prefixed_images = [f"data:image/jpeg;base64,{img}" for img in image_data]
            cache.set(cache_key, prefixed_images, timeout)
            logger.info(f"Image stored in cache with key: {cache_key}")
            return True
        except Exception as e:
            logger.error(f"Error storing image: {str(e)}")
            return False

    @staticmethod
    def get_image(kiosk_uuid: str, image_uuid: str) -> Optional[list[str]]:
        """
        Retrieve image from cache
        :param kiosk_uuid: Kiosk identifier
        :param image_uuid: Image identifier
        :return: Base64 encoded image data if found, None otherwise
        """
        cache_key = f"image_{kiosk_uuid}_{image_uuid}"
        image = cache.get(cache_key)
        if image:
            logger.info(f"Retrieved image from cache with key: {cache_key}")
        else:
            logger.warning(f"No image found in cache for key: {cache_key}")
        return image

    @staticmethod
    def delete_image(kiosk_uuid: str, image_uuid: str) -> bool:
        """
        Delete image from cache
        :return: Base64 encoded image data if found, None otherwise
        :param image_uuid: Image identifier
        :return: True if deleted successfully
        """
        cache_key = f"image_{kiosk_uuid}_{image_uuid}"
        result = cache.delete(cache_key)
        if result:
            logger.info(f"Deleted image from cache with key: {cache_key}")
        else:
            logger.warning(f"No image found to delete for key: {cache_key}")
        return result

class PayPalService:
    def __init__(self):
        paypalrestsdk.configure({
            "mode": settings.PAYPAL_MODE,
            "client_id": settings.PAYPAL_CLIENT_ID,
            "client_secret": settings.PAYPAL_CLIENT_SECRET
        })

    def create_payment(self, transaction_id, kiosk_id, price, num_pictures):
        # Create an order in the database
        order = Order.objects.create(
            transaction_id=transaction_id,
            kiosk_id=kiosk_id,
            price=price,
            num_pictures=num_pictures
        )

        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {
                "payment_method": "paypal"
            },
            "redirect_urls": {
                "return_url": "https://kiosk-python-backend-soyf8.ondigitalocean.app/api/payment/execute/",
                "cancel_url": "https://kiosk-python-backend-soyf8.ondigitalocean.app/api/payment/cancel/"
            },
            "transactions": [{
                "item_list": {
                    "items": [{
                        "name": f"Pictures ({num_pictures})",
                        "sku": transaction_id,
                        "price": str(price),
                        "currency": "USD",
                        "quantity": 1
                    }]
                },
                "amount": {
                    "total": str(price),
                    "currency": "USD"
                },
                "description": f"Payment for kiosk {kiosk_id}"
            }]
        })

        if payment.create():
            order.paypal_payment_id = payment.id
            order.save()
            logger.info(f"Payment created successfully for transaction {transaction_id}")
            return payment
        else:
            logger.error(f"Error while creating payment: {payment.error}")
            return None

    def execute_payment(self, payment_id, payer_id):
        payment = paypalrestsdk.Payment.find(payment_id)
        if payment.execute({"payer_id": payer_id}):
            logger.info(f"Payment executed successfully for payment ID {payment_id}")
            return payment
        else:
            logger.error(f"Error while executing payment: {payment.error}")
            return None