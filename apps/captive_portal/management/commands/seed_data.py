from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from openwisp_users.models import Organization
from django.contrib.sites.models import Site
from django.conf import settings
# Use RadiusGroupCheck/Reply which were used in older openwisp-radius versions
# This is to fix the FieldError where RadiusCheck has no 'group' or 'groupname' field
from openwisp_radius.models import RadiusGroup, RadiusGroupCheck, RadiusGroupReply
from apps.captive_portal.models import WiFiPackage

User = get_user_model()

class Command(BaseCommand):
    help = "Seed database with test data for OpenWISP, Radius, and Captive Portal"

    def handle(self, *args, **options):
        self.stdout.write("Starting data seeding...")

        with transaction.atomic():
            # 1. Organization (OpenWISP requirement)
            org, created = Organization.objects.get_or_create(
                slug='default',
                defaults={'name': 'Default Organization'}
            )
            self.log_action(created, f"Organization '{org.name}'")

            # Ensure the default Site object exists to prevent admin login errors
            site, created = Site.objects.update_or_create(
                id=settings.SITE_ID,
                defaults={
                    'domain': 'example.com',
                    'name': 'Netmon'
                }
            )
            self.log_action(created, f"Site '{site.name}'")

            # 2. Define all packages from sasakonnect.net/packages
            package_definitions = [
                {
                    'name': 'Daily 1GB', 'price': 30, 'duration_days': 1, 'data_gb': 1,
                    'bandwidth_mbps': 10
                },
                {
                    'name': 'Daily 3GB', 'price': 50, 'duration_days': 1, 'data_gb': 3,
                    'bandwidth_mbps': 10
                },
                {
                    'name': 'Weekly 8GB', 'price': 250, 'duration_days': 7, 'data_gb': 8,
                    'bandwidth_mbps': 10
                },
                {
                    'name': 'Weekly 15GB', 'price': 500, 'duration_days': 7, 'data_gb': 15,
                    'bandwidth_mbps': 10
                },
                {
                    'name': 'Monthly 30GB', 'price': 1000, 'duration_days': 30, 'data_gb': 30,
                    'bandwidth_mbps': 10
                },
                {
                    'name': 'Monthly 50GB', 'price': 1500, 'duration_days': 30, 'data_gb': 50,
                    'bandwidth_mbps': 10
                },
            ]

            self.stdout.write("Deleting old WiFi packages to ensure a clean slate...")
            WiFiPackage.objects.all().delete()
            # Note: We are not deleting RadiusGroups to avoid breaking existing user associations
            # if the script is run multiple times. `get_or_create` handles this.

            for pkg_def in package_definitions:
                # Generate a unique radius group name
                radius_group_name = f"{pkg_def['duration_days']}day-{pkg_def['data_gb']}gb-{pkg_def['bandwidth_mbps']}mbps".lower().replace(" ", "")

                # Calculate technical values
                session_timeout = pkg_def['duration_days'] * 24 * 60 * 60
                bandwidth_bps = pkg_def['bandwidth_mbps'] * 1024 * 1024
                data_limit_bytes = pkg_def['data_gb'] * 1024 * 1024 * 1024
                duration_minutes = pkg_def['duration_days'] * 24 * 60
                data_limit_mb = pkg_def['data_gb'] * 1024

                # 3. Create or Update Radius Group
                group, created = RadiusGroup.objects.get_or_create(
                    name=radius_group_name,
                    organization=org,
                    defaults={'description': f"{pkg_def['name']} @ {pkg_def['bandwidth_mbps']}Mbps"}
                )
                self.log_action(created, f"Radius Group '{group.name}'")
                self.set_radius_attributes(
                    group,
                    session_timeout=session_timeout,
                    bandwidth_bps=bandwidth_bps,
                    data_limit_bytes=data_limit_bytes
                )

                # 4. Create WiFi Package
                pkg, created = WiFiPackage.objects.update_or_create(
                    name=pkg_def['name'],  # Use name as the unique key for packages
                    defaults={
                        'price': pkg_def['price'],
                        'duration_minutes': duration_minutes,
                        'data_limit_mb': data_limit_mb,
                        'radius_group_name': radius_group_name,
                    }
                )
                self.log_action(created, f"WiFiPackage '{pkg.name}'")

            # 5. Users
            # Superuser
            admin_phone = '0700000000'
            if not User.objects.filter(phone_number=admin_phone).exists():
                User.objects.create_superuser(
                    phone_number=admin_phone,
                    password='adminpassword',
                    email='admin@example.com'
                )
                self.stdout.write(self.style.SUCCESS(f"Created Superuser: {admin_phone} / adminpassword"))
            
            # Standard User
            user_phone = '0711111111'
            if not User.objects.filter(phone_number=user_phone).exists():
                User.objects.create_user(
                    phone_number=user_phone,
                    password='userpassword',
                    email='user@example.com'
                )
                self.stdout.write(self.style.SUCCESS(f"Created User: {user_phone} / userpassword"))

        self.stdout.write(self.style.SUCCESS("Data seeding completed successfully."))

    def set_radius_attributes(self, group, session_timeout, bandwidth_bps, data_limit_bytes=None):
        """Helper to set standard RADIUS attributes for a group."""
        # Max Session Time (Session-Timeout)
        RadiusGroupCheck.objects.update_or_create(
            groupname=group.name,
            attribute='Session-Timeout',
            defaults={'op': ':=', 'value': str(session_timeout)}
        )

        # Data limit (total octets = upload + download)
        # Note: The RADIUS attribute for data limit can vary by NAS vendor.
        # 'ChilliSpot-Max-Total-Octets' is common for CoovaChilli.
        # Another option is 'Max-All-Session' with FreeRADIUS.
        if data_limit_bytes:
            RadiusGroupCheck.objects.update_or_create(
                groupname=group.name,
                attribute='ChilliSpot-Max-Total-Octets',
                defaults={'op': ':=', 'value': str(data_limit_bytes)}
            )

        # Bandwidth Down (WISPr)
        RadiusGroupReply.objects.update_or_create(
            groupname=group.name,
            attribute='WISPr-Bandwidth-Max-Down',
            defaults={'op': ':=', 'value': str(bandwidth_bps)}
        )
        # Bandwidth Up (WISPr)
        RadiusGroupReply.objects.update_or_create(
            groupname=group.name,
            attribute='WISPr-Bandwidth-Max-Up',
            defaults={'op': ':=', 'value': str(bandwidth_bps)}
        )

    def log_action(self, created, name):
        action = "Created" if created else "Updated"
        self.stdout.write(f"{action} {name}")