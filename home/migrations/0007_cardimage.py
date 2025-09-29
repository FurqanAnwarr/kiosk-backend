from django.db import migrations, models
import uuid

class Migration(migrations.Migration):

    dependencies = [
        ('home', '0006_order_alter_kioskhealthcheck_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='CardImage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('image', models.ImageField(upload_to='cards/')),
                ('version', models.PositiveIntegerField(default=1)),
                ('is_enabled', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Card Image',
                'verbose_name_plural': 'Card Images',
            },
        ),
    ] 