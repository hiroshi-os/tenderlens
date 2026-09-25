from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from alerts.forms import AlertForm, SavedSearchForm
from alerts.models import Alert, Notification, SavedSearch
from tenders.search import tenders_matching


@login_required
def search_list(request):
    form = SavedSearchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.user = request.user
        saved.save()
        messages.success(request, "Search saved.")
        return redirect("searches")
    searches = []
    for saved in request.user.saved_searches.all():
        searches.append({"saved": saved, "count": tenders_matching(saved.as_filters()).count()})
    return render(request, "alerts/searches.html", {"form": form, "searches": searches})


@login_required
@require_POST
def search_delete(request, pk):
    saved = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    saved.delete()
    messages.success(request, "Search removed.")
    return redirect("searches")


@login_required
def alert_list(request):
    form = AlertForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["channel"] == Alert.Channel.EMAIL and not request.user.email:
            form.add_error("channel", "Add an email address to your account before choosing email.")
        else:
            alert = form.save(commit=False)
            alert.user = request.user
            alert.save()
            messages.success(request, "Alert saved. It runs after each ingest.")
            return redirect("alerts")
    return render(
        request, "alerts/alerts.html", {"form": form, "alerts": request.user.alerts.all()}
    )


@login_required
@require_POST
def alert_from_search(request, pk):
    saved = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    channel = request.POST.get("channel", Alert.Channel.IN_APP)
    if channel not in Alert.Channel.values:
        channel = Alert.Channel.IN_APP
    if channel == Alert.Channel.EMAIL and not request.user.email:
        messages.error(request, "Add an email address before creating an email alert.")
        return redirect("searches")
    Alert.objects.create(
        user=request.user,
        saved_search=saved,
        name=saved.name,
        channel=channel,
        keywords=saved.keywords,
        category=saved.category,
        state=saved.state,
        ministry=saved.ministry,
        min_value=saved.min_value,
        max_value=saved.max_value,
        closing_before=saved.closing_before,
    )
    messages.success(request, "Alert linked to that saved search.")
    return redirect("alerts")


@login_required
@require_POST
def alert_delete(request, pk):
    alert = get_object_or_404(Alert, pk=pk, user=request.user)
    alert.delete()
    messages.success(request, "Alert removed.")
    return redirect("alerts")


@login_required
def notification_list(request):
    notes = Notification.objects.filter(user=request.user).select_related("tender", "alert")
    return render(request, "alerts/notifications.html", {"notifications": notes})


@login_required
@require_POST
def notification_read(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    note.status = Notification.Status.READ
    note.read_at = timezone.now()
    note.save(update_fields=["status", "read_at"])
    return redirect("tender_detail", pk=note.tender_id)
