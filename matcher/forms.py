from django import forms
from allauth.account.forms import SignupForm

from .models import UserProfile

class UploadFilesForm(forms.Form):
    fd_file = forms.FileField(label="Bank Statement File (Excel)")
    gl_file = forms.FileField(label="General Ledger File (Excel)")
    third_file = forms.FileField(label="Last Reconciled File (Excel)")


class CustomSignupForm(SignupForm):
    account_type = forms.ChoiceField(
        choices=UserProfile.ACCOUNT_TYPE_CHOICES,
        label="Account type",
    )
    full_name = forms.CharField(max_length=150, label="Full name")
    company_name = forms.CharField(max_length=150, required=False, label="Company name")
    phone_number = forms.CharField(max_length=30, required=False, label="Phone number")
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "password1" in self.fields:
            self.fields["password1"].help_text = ""

    def signup(self, request, user):
        UserProfile.objects.update_or_create(
            user=user,
            defaults={
                "account_type": self.cleaned_data["account_type"],
                "full_name": self.cleaned_data["full_name"],
                "company_name": self.cleaned_data.get("company_name", ""),
                "phone_number": self.cleaned_data.get("phone_number", ""),
                "address": self.cleaned_data.get("address", ""),
            },
        )

        return user
