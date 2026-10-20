"""Health + Prometheus endpoints."""

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.common.metrics import render_metrics


@require_GET
def health(request):
    return JsonResponse({"status": "ok", "service": "aits-backend", "version": "2.0.0"})


@csrf_exempt
@require_GET
def metrics(request):
    return HttpResponse(render_metrics(), content_type="text/plain; version=0.0.4; charset=utf-8")
