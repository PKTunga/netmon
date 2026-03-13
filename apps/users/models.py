from django.db import models
from django.contrib.auth.models import BaseUserManager
from django.utils.translation import gettext_lazy as _
from openwisp_users.models import AbstractUser


class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where phone number is the unique identifier
    for authentication instead of usernames.
    """
    def create_user(self, phone_number, password, **extra_fields):
        """
        Create and save a User with the given phone number and password.
        """
        if not phone_number:
            raise ValueError(_('The Phone Number must be set'))
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password, **extra_fields):
        """
        Create and save a SuperUser with the given phone number and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        return self.create_user(phone_number, password, **extra_fields)


class CustomUser(AbstractUser):
    # Override fields from AbstractUser to make them optional, as we use phone_number
    username = models.CharField(_('username'), max_length=150, unique=True, null=True, blank=True)
    email = models.EmailField(_('email address'), blank=True, null=True, unique=True)
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name=_('groups'),
        blank=True,
        help_text=_(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        related_name="custom_user_set",
        related_query_name="custom_user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name=_('user permissions'),
        blank=True,
        help_text=_('Specific permissions for this user.'),
        related_name="custom_user_set",
        related_query_name="custom_user",
    )

    # Explicitly override fields to allow nulls, matching the initial migration
    location = models.CharField(_('location'), max_length=256, blank=True, null=True)
    birth_date = models.DateField(_('birth date'), blank=True, null=True)
    notes = models.TextField(_('notes'), blank=True, null=True)
    language = models.CharField(_('language'), max_length=8, blank=True, null=True, choices=[('en', 'English')])

    # Add our custom field
    phone_number = models.CharField(_('phone number'), max_length=15, unique=True)

    USERNAME_FIELD = 'phone_number'
    # openwisp_users.AbstractUser has REQUIRED_FIELDS = ['email'], we override it
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.phone_number
    
    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.phone_number
        super().save(*args, **kwargs)

    class Meta(AbstractUser.Meta):
        swappable = 'AUTH_USER_MODEL'
        indexes = [
            models.Index(fields=['email'], name='custom_user_email_idx')
        ]