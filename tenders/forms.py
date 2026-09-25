from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class SearchForm(forms.Form):
    q = forms.CharField(required=False, label="Keywords", max_length=300)
    category = forms.CharField(required=False, max_length=400)
    state = forms.CharField(required=False, max_length=100)
    ministry = forms.CharField(required=False, max_length=400)
    min_value = forms.DecimalField(required=False, min_value=0, label="Min value (INR)")
    max_value = forms.DecimalField(required=False, min_value=0, label="Max value (INR)")
    closing_before = forms.DateField(
        required=False, label="Closes on or before", widget=forms.DateInput(attrs={"type": "date"})
    )

    def filters(self) -> dict:
        cleaned = self.cleaned_data
        return {
            "q": cleaned.get("q") or "",
            "category": cleaned.get("category") or "",
            "state": cleaned.get("state") or "",
            "ministry": cleaned.get("ministry") or "",
            "min_value": cleaned.get("min_value"),
            "max_value": cleaned.get("max_value"),
            "closing_before": cleaned.get("closing_before"),
        }


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
