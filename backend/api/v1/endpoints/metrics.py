"""
Prometheus Metrics API Endpoint

Exposes /metrics in Prometheus text exposition format for scraping
by Prometheus, Grafana Agent, or any compatible collector.

Epic E8-S1: Prometheus Metrics Exporter
Refs: #49
"""

import logging

from fastapi import APIRouter
from fastapi.responses import Response

from backend.services.prometheus_metrics_service import get_metrics_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["Metrics", "Monitoring"])

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get(
    "",
    summary="Prometheus metrics endpoint",
    description=(
        "Returns all OpenClaw metrics in Prometheus exposition format. "
        "Suitable for scraping by Prometheus, Grafana Agent, or any "
        "compatible metrics collector."
    ),
    responses={
        200: {
            "description": "Metrics in Prometheus text format",
            "content": {"text/plain": {}},
        },
    },
)
async def get_metrics() -> Response:
    """
    Get Prometheus metrics.

    Pulls latest gauge values from registered services,
    then returns all metrics in Prometheus text format.
    """
    service = get_metrics_service()
    service.collect_service_stats()
    content = service.generate_metrics()
    return Response(content=content, media_type=PROMETHEUS_CONTENT_TYPE)
