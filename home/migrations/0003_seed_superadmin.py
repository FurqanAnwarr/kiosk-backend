from django.db import migrations
from django.contrib.auth import get_user_model

def create_superadmin(apps, schema_editor):
    User = get_user_model()
    if not User.objects.filter(username='superadmin').exists():
        User.objects.create_superuser(
            username='superadmin',
            email='superadmin@example.com',
            password='superadminpassword'
        )

class Migration(migrations.Migration):

    dependencies = [
        ('home', '0002_kioskconfiguration'),
    ]

    operations = [
        migrations.RunPython(create_superadmin),
    ]
