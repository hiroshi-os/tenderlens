from django import forms

from alerts.models import Alert, SavedSearch


class SavedSearchForm(forms.ModelForm):
    class Meta:
        model = SavedSearch
        fields = (
            "name",
            "keywords",
            "category",
            "state",
            "ministry",
            "min_value",
            "max_value",
            "closing_before",
        )
        widgets = {"closing_before": forms.DateInput(attrs={"type": "date"})}


class AlertForm(forms.ModelForm):
    class Meta:
        model = Alert
        fields = (
            "name",
            "keywords",
            "category",
            "state",
            "ministry",
            "min_value",
            "max_value",
            "closing_before",
            "channel",
            "is_active",
        )
        widgets = {"closing_before": forms.DateInput(attrs={"type": "date"})}
