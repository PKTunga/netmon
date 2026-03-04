from django.db import models
from django.conf import settings

class WiFiPackage(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_minutes = models.IntegerField(help_text="Duration in minutes")
    data_limit_mb = models.IntegerField(null=True, blank=True, help_text="Data limit in MB")
    description = models.TextField(blank=True)
    radius_group_name = models.CharField(max_length=64, default="default", help_text="OpenWISP Radius Group to assign")

    def __str__(self):
        return f"{self.name} - {self.price}"

class PaymentTransaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    package = models.ForeignKey(WiFiPackage, on_delete=models.SET_NULL, null=True)
    phone_number = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    checkout_request_id = models.CharField(max_length=100, unique=True)
    mpesa_receipt_number = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(max_length=20, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.phone_number} - {self.status}"