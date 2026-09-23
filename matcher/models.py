from django.db import models
from django.conf import settings

class UserProfile(models.Model):
    ACCOUNT_TYPE_COMPANY = "company"
    ACCOUNT_TYPE_PERSONAL = "personal"

    ACCOUNT_TYPE_CHOICES = [
        (ACCOUNT_TYPE_COMPANY, "Company"),
        (ACCOUNT_TYPE_PERSONAL, "Personal"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        default=ACCOUNT_TYPE_COMPANY,
    )
    full_name = models.CharField(max_length=150)
    company_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.company_name:
            return self.company_name

        return self.full_name
