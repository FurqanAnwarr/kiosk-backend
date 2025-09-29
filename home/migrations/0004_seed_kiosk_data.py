from django.db import migrations
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

def create_kiosk_data(apps, schema_editor):
    User = get_user_model()
    KioskClient = apps.get_model('home', 'KioskClient')
    KioskConfiguration = apps.get_model('home', 'KioskConfiguration')
    
    kiosk_client, created = KioskClient.objects.get_or_create(
        login_name='kiosk',
        defaults={
            'password_hash': make_password('kiosk_password'),
            'is_active': True
        }
    )
    
    # Create a KioskConfiguration for the KioskClient
    if created or not hasattr(kiosk_client, 'configuration'):
        KioskConfiguration.objects.get_or_create(
            kiosk=kiosk_client,
            defaults={
                'location_name': 'Default Location',
                'theme': 'light',
                'idle_timeout_seconds': 300,
                'allow_printer': False,
                'custom_header': 'Welcome to the Kiosk',
                'maintenance_mode': False
            }
        )

class Migration(migrations.Migration):

    dependencies = [
        ('home', '0003_seed_superadmin'),
    ]

    operations = [
        migrations.RunPython(create_kiosk_data),
    ]