from django.db import migrations


def create_default_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name="Administrator")
    Group.objects.get_or_create(name="Operator")

    # Create default organization for openwisp_radius dependency
    Organization = apps.get_model('openwisp_users', 'Organization')
    if not Organization.objects.exists():
        Organization.objects.create(name='default', slug='default')


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_placeholder'),
        ('openwisp_users', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_default_groups),
    ]