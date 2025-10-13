from django.db import models
from django.contrib.auth.hashers import make_password, check_password
import uuid
from django.core.exceptions import ValidationError
from django.utils import timezone
import os

import stripe

class KioskClient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    login_name = models.CharField(max_length=100, unique=True)
    password_hash = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Authentication properties
    is_authenticated = True
    is_anonymous = False

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

    def __str__(self):
        return f"Kiosk: {self.login_name}"

    class Meta:
        verbose_name = "Kiosk Client"
        verbose_name_plural = "Kiosk Clients"

class KioskConfiguration(models.Model):
    THEME_CHOICES = [
        ('light', 'Light Theme'),
        ('dark', 'Dark Theme'),
        ('custom', 'Custom Theme')
    ]

    kiosk = models.OneToOneField(
        KioskClient,
        on_delete=models.CASCADE,
        related_name='configuration'
    )
    location_name = models.CharField(max_length=200, help_text="Physical location of the kiosk")
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='light')
    idle_timeout_seconds = models.IntegerField(
        default=300,
        help_text="Time in seconds before the kiosk returns to home screen"
    )
    allow_printer = models.BooleanField(default=False, help_text="Allow printing functionality")
    custom_header = models.CharField(
        max_length=200,
        blank=True,
        help_text="Custom header text to display on the kiosk"
    )
    maintenance_mode = models.BooleanField(
        default=False,
        help_text="Put kiosk in maintenance mode"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Configuration for {self.kiosk.login_name}"

    class Meta:
        verbose_name = "Kiosk Configuration"
        verbose_name_plural = "Kiosk Configurations"

class KioskHealthCheck(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kiosk = models.OneToOneField(KioskClient, on_delete=models.CASCADE, related_name='health_check')
    last_checked = models.DateTimeField(auto_now=True)
    is_healthy = models.BooleanField(default=True)
    health_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Health Check for {self.kiosk.login_name}"

class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.CharField(max_length=100, unique=True)
    kiosk_id = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    num_pictures = models.IntegerField()
    status = models.CharField(max_length=50, default='created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paypal_payment_id = models.CharField(max_length=100, blank=True, null=True)
    paypal_payer_id = models.CharField(max_length=100, blank=True, null=True)
    paypal_response = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"Order {self.transaction_id} - {self.status}"


def card_image_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    return f'cards/{instance.id}.{ext}'

class KioskDevice(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("disabled", "Disabled"),
    ]

    kiosk_id = models.CharField(max_length=64, unique=True, blank=False, null=False)
    secret_key_hash = models.CharField(max_length=128, blank=False, null=False)
    location = models.CharField(max_length=255, blank=True, null=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    registered_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    allowed_lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    allowed_lng = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    allowed_radius = models.IntegerField(default=500)  # in meters
    hardware_hash = models.CharField(max_length=128, blank=True, null=True)

    def __str__(self):
        return f"Kiosk {self.kiosk_id} ({self.status})"


class ReaderDevice(models.Model):
    reader_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=100, unique=True)
    country = models.CharField(max_length=16)
    city = models.CharField(max_length=16)
    state = models.CharField(max_length=16)
    address = models.CharField(max_length=16)
    postalCode = models.CharField(max_length=10)
    kiosk = models.ForeignKey("home.KioskDevice", related_name="readers", on_delete=models.SET_NULL, null=True, blank=True)
    stripe_location_id = models.CharField(max_length=64, blank=True, null=True)  # ✅ Added
    registered_at = models.DateTimeField(default=timezone.now)

    def clean(self):
        required_fields = ["country", "city", "state", "address", "postalCode", "reader_id", "name"]
        for field in required_fields:
            if not getattr(self, field):
                raise ValidationError(f"{field} is required")

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new = self.pk is None

        if is_new:
            try:
                # Create Stripe Location
                location = stripe.terminal.Location.create(
                    display_name=self.name,
                    address={
                        "line1": self.address,
                        "city": self.city,
                        "state": self.state,
                        "country": self.country,
                        "postal_code": self.postalCode,
                    },
                )
                self.stripe_location_id = location.id

                # Register Reader Device
                reader = stripe.terminal.Reader.create(
                    registration_code=self.reader_id,
                    label=self.name,
                    location=self.stripe_location_id,
                )

                # Store Stripe reader ID (optional)
                self.reader_id = reader.id
            except Exception as e:
                raise ValidationError(f"Stripe registration failed: {str(e)}")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Reader {self.name} ({self.reader_id})"

class CardImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ImageField(upload_to=card_image_upload_path)
    version = models.PositiveIntegerField(default=1, editable=False)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)

        if self.image and not self.image.name.startswith(f'cards/{self.id}'):
            ext = os.path.splitext(self.image.name)[1]
            self.image.name = f'cards/{self.id}{ext}'

        self.version += 1 if self.pk else 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Card {self.id} (v{self.version})"

    class Meta:
        verbose_name = "Card Image"
        verbose_name_plural = "Card Images"
