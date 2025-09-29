from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('home', '0007_cardimage'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cardimage',
            name='title',
        ),
        migrations.RemoveField(
            model_name='cardimage',
            name='description',
        ),
        migrations.AlterField(
            model_name='cardimage',
            name='version',
            field=models.PositiveIntegerField(default=1, editable=False),
        ),
    ] 