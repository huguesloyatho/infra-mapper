"""Middleware de collecte des métriques internes du backend."""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, List, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


@dataclass
class RequestMetrics:
    """Métriques d'une requête."""
    method: str
    path: str
    status_code: int
    duration_ms: float
    timestamp: datetime


@dataclass
class EndpointStats:
    """Statistiques agrégées pour un endpoint."""
    request_count: int = 0
    error_count: int = 0  # 4xx et 5xx
    total_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0

    @property
    def avg_duration_ms(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.total_duration_ms / self.request_count


class InternalMetricsCollector:
    """Collecteur de métriques internes thread-safe."""

    # Singleton
    _instance: Optional['InternalMetricsCollector'] = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._metrics_lock = Lock()

        # Métriques par endpoint (method:path)
        self._endpoint_stats: Dict[str, EndpointStats] = defaultdict(EndpointStats)

        # Historique récent (dernières 5 minutes) pour calculs de taux
        self._recent_requests: List[RequestMetrics] = []
        self._recent_window = timedelta(minutes=5)

        # Compteurs globaux
        self._total_requests = 0
        self._total_errors = 0
        self._start_time = datetime.utcnow()

        # Histogramme de latence (buckets en ms)
        self._latency_buckets = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
        self._latency_histogram: Dict[str, int] = {f"le_{b}": 0 for b in self._latency_buckets}
        self._latency_histogram["le_inf"] = 0

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float):
        """Enregistre une requête."""
        with self._metrics_lock:
            now = datetime.utcnow()

            # Normaliser le path (enlever les IDs dynamiques)
            normalized_path = self._normalize_path(path)
            endpoint_key = f"{method}:{normalized_path}"

            # Mettre à jour les stats de l'endpoint
            stats = self._endpoint_stats[endpoint_key]
            stats.request_count += 1
            stats.total_duration_ms += duration_ms
            stats.min_duration_ms = min(stats.min_duration_ms, duration_ms)
            stats.max_duration_ms = max(stats.max_duration_ms, duration_ms)

            if status_code >= 400:
                stats.error_count += 1
                self._total_errors += 1

            # Compteurs globaux
            self._total_requests += 1

            # Histogramme de latence
            for bucket in self._latency_buckets:
                if duration_ms <= bucket:
                    self._latency_histogram[f"le_{bucket}"] += 1
                    break
            else:
                self._latency_histogram["le_inf"] += 1

            # Ajouter à l'historique récent
            metric = RequestMetrics(
                method=method,
                path=normalized_path,
                status_code=status_code,
                duration_ms=duration_ms,
                timestamp=now
            )
            self._recent_requests.append(metric)

            # Nettoyer l'historique ancien
            cutoff = now - self._recent_window
            self._recent_requests = [m for m in self._recent_requests if m.timestamp > cutoff]

    def _normalize_path(self, path: str) -> str:
        """Normalise un path en remplaçant les IDs par des placeholders."""
        import re
        # UUIDs
        path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{id}', path)
        # IDs numériques
        path = re.sub(r'/\d+', '/{id}', path)
        # Host IDs (hostname-hexcode)
        path = re.sub(r'/[a-zA-Z0-9_-]+-[0-9a-f]{8}', '/{host_id}', path)
        return path

    def get_stats(self) -> dict:
        """Retourne les statistiques actuelles."""
        with self._metrics_lock:
            now = datetime.utcnow()
            uptime = (now - self._start_time).total_seconds()

            # Calculer le taux de requêtes sur la fenêtre récente
            recent_count = len(self._recent_requests)
            window_seconds = self._recent_window.total_seconds()
            requests_per_second = recent_count / window_seconds if window_seconds > 0 else 0

            # Erreurs récentes
            recent_errors = sum(1 for m in self._recent_requests if m.status_code >= 400)
            error_rate = (recent_errors / recent_count * 100) if recent_count > 0 else 0

            # Top endpoints par nombre de requêtes
            top_endpoints = sorted(
                self._endpoint_stats.items(),
                key=lambda x: x[1].request_count,
                reverse=True
            )[:10]

            # Endpoints les plus lents
            slowest_endpoints = sorted(
                [(k, v) for k, v in self._endpoint_stats.items() if v.request_count > 0],
                key=lambda x: x[1].avg_duration_ms,
                reverse=True
            )[:10]

            return {
                "uptime_seconds": uptime,
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "requests_per_second": round(requests_per_second, 2),
                "error_rate_percent": round(error_rate, 2),
                "recent_window_minutes": self._recent_window.total_seconds() / 60,
                "top_endpoints": [
                    {
                        "endpoint": k,
                        "requests": v.request_count,
                        "errors": v.error_count,
                        "avg_ms": round(v.avg_duration_ms, 2),
                        "min_ms": round(v.min_duration_ms, 2) if v.min_duration_ms != float('inf') else 0,
                        "max_ms": round(v.max_duration_ms, 2),
                    }
                    for k, v in top_endpoints
                ],
                "slowest_endpoints": [
                    {
                        "endpoint": k,
                        "avg_ms": round(v.avg_duration_ms, 2),
                        "requests": v.request_count,
                    }
                    for k, v in slowest_endpoints
                ],
            }

    def export_prometheus(self) -> str:
        """Exporte les métriques internes au format Prometheus."""
        lines = []

        with self._metrics_lock:
            uptime = (datetime.utcnow() - self._start_time).total_seconds()

            # Métriques globales
            lines.append(f"# HELP infra_backend_uptime_seconds Backend uptime in seconds")
            lines.append(f"# TYPE infra_backend_uptime_seconds gauge")
            lines.append(f"infra_backend_uptime_seconds {uptime:.2f}")

            lines.append(f"# HELP infra_backend_requests_total Total number of HTTP requests")
            lines.append(f"# TYPE infra_backend_requests_total counter")
            lines.append(f"infra_backend_requests_total {self._total_requests}")

            lines.append(f"# HELP infra_backend_errors_total Total number of HTTP errors (4xx, 5xx)")
            lines.append(f"# TYPE infra_backend_errors_total counter")
            lines.append(f"infra_backend_errors_total {self._total_errors}")

            # Histogramme de latence
            lines.append(f"# HELP infra_backend_request_duration_ms_bucket Request duration histogram")
            lines.append(f"# TYPE infra_backend_request_duration_ms_bucket histogram")
            cumulative = 0
            for bucket in self._latency_buckets:
                cumulative += self._latency_histogram[f"le_{bucket}"]
                lines.append(f'infra_backend_request_duration_ms_bucket{{le="{bucket}"}} {cumulative}')
            cumulative += self._latency_histogram["le_inf"]
            lines.append(f'infra_backend_request_duration_ms_bucket{{le="+Inf"}} {cumulative}')

            # Métriques par endpoint
            lines.append(f"# HELP infra_backend_endpoint_requests_total Requests per endpoint")
            lines.append(f"# TYPE infra_backend_endpoint_requests_total counter")
            for endpoint, stats in self._endpoint_stats.items():
                method, path = endpoint.split(":", 1)
                lines.append(
                    f'infra_backend_endpoint_requests_total{{method="{method}",path="{path}"}} {stats.request_count}'
                )

            lines.append(f"# HELP infra_backend_endpoint_errors_total Errors per endpoint")
            lines.append(f"# TYPE infra_backend_endpoint_errors_total counter")
            for endpoint, stats in self._endpoint_stats.items():
                if stats.error_count > 0:
                    method, path = endpoint.split(":", 1)
                    lines.append(
                        f'infra_backend_endpoint_errors_total{{method="{method}",path="{path}"}} {stats.error_count}'
                    )

            lines.append(f"# HELP infra_backend_endpoint_duration_avg_ms Average request duration per endpoint")
            lines.append(f"# TYPE infra_backend_endpoint_duration_avg_ms gauge")
            for endpoint, stats in self._endpoint_stats.items():
                if stats.request_count > 0:
                    method, path = endpoint.split(":", 1)
                    lines.append(
                        f'infra_backend_endpoint_duration_avg_ms{{method="{method}",path="{path}"}} {stats.avg_duration_ms:.2f}'
                    )

        return "\n".join(lines)


# Instance globale
metrics_collector = InternalMetricsCollector()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware qui collecte les métriques de chaque requête."""

    # Paths à exclure des métriques (health checks, métriques elles-mêmes)
    EXCLUDED_PATHS = {"/health", "/api/v1/metrics/prometheus", "/api/v1/internal/metrics"}

    async def dispatch(self, request: Request, call_next) -> Response:
        # Exclure certains paths
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        metrics_collector.record_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms
        )

        return response
