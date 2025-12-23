"""Scheduled reports routes for Infra-Mapper."""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import (
    ScheduledReport, ReportHistory,
    ReportFrequency, ReportFormat, ReportType
)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ReportDestinationConfig(BaseModel):
    """Configuration de destination du rapport."""
    recipients: Optional[List[str]] = None  # Pour email
    subject_prefix: Optional[str] = "[Infra-Mapper]"
    url: Optional[str] = None  # Pour webhook
    method: Optional[str] = "POST"
    headers: Optional[dict] = None
    path: Optional[str] = None  # Pour storage
    retention_days: Optional[int] = 30


class ScheduledReportCreate(BaseModel):
    """Schéma pour créer un rapport planifié."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    report_type: ReportType
    report_format: ReportFormat = ReportFormat.JSON
    frequency: ReportFrequency
    schedule_hour: int = Field(default=8, ge=0, le=23)
    schedule_day: Optional[int] = Field(default=None, ge=0, le=31)
    host_filter: Optional[str] = None
    project_filter: Optional[str] = None
    include_offline: bool = True
    destination_type: str = "email"
    destination_config: ReportDestinationConfig = Field(default_factory=ReportDestinationConfig)


class ScheduledReportUpdate(BaseModel):
    """Schéma pour mettre à jour un rapport planifié."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    report_type: Optional[ReportType] = None
    report_format: Optional[ReportFormat] = None
    frequency: Optional[ReportFrequency] = None
    schedule_hour: Optional[int] = Field(None, ge=0, le=23)
    schedule_day: Optional[int] = Field(None, ge=0, le=31)
    host_filter: Optional[str] = None
    project_filter: Optional[str] = None
    include_offline: Optional[bool] = None
    destination_type: Optional[str] = None
    destination_config: Optional[ReportDestinationConfig] = None
    enabled: Optional[bool] = None


class ScheduledReportResponse(BaseModel):
    """Réponse pour un rapport planifié."""
    id: str
    name: str
    description: Optional[str]
    enabled: bool
    report_type: str
    report_format: str
    frequency: str
    schedule_hour: int
    schedule_day: Optional[int]
    host_filter: Optional[str]
    project_filter: Optional[str]
    include_offline: bool
    destination_type: str
    destination_config: dict
    last_run_at: Optional[datetime]
    last_run_status: Optional[str]
    next_run_at: Optional[datetime]
    runs_count: int
    success_count: int
    error_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ReportHistoryResponse(BaseModel):
    """Réponse pour l'historique d'un rapport."""
    id: int
    report_id: str
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    error_message: Optional[str]
    file_path: Optional[str]
    file_size: Optional[int]
    stats: dict

    class Config:
        from_attributes = True


# =============================================================================
# Helper Functions
# =============================================================================

def calculate_next_run(frequency: ReportFrequency, schedule_hour: int, schedule_day: Optional[int]) -> datetime:
    """Calcule la prochaine exécution du rapport."""
    now = datetime.utcnow()

    if frequency == ReportFrequency.DAILY:
        next_run = now.replace(hour=schedule_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

    elif frequency == ReportFrequency.WEEKLY:
        # schedule_day = 0-6 (lundi-dimanche)
        day_of_week = schedule_day if schedule_day is not None else 0
        days_ahead = day_of_week - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and now.hour >= schedule_hour):
            days_ahead += 7
        next_run = now.replace(hour=schedule_hour, minute=0, second=0, microsecond=0)
        next_run += timedelta(days=days_ahead)

    elif frequency == ReportFrequency.MONTHLY:
        # schedule_day = 1-31
        day_of_month = schedule_day if schedule_day is not None else 1
        next_run = now.replace(day=min(day_of_month, 28), hour=schedule_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            # Passer au mois suivant
            if now.month == 12:
                next_run = next_run.replace(year=now.year + 1, month=1)
            else:
                next_run = next_run.replace(month=now.month + 1)

    return next_run


# =============================================================================
# Routes
# =============================================================================

@router.get("/scheduled", response_model=List[ScheduledReportResponse])
async def list_scheduled_reports(
    db: AsyncSession = Depends(get_db),
    enabled_only: bool = Query(False, description="Only show enabled reports"),
):
    """Liste tous les rapports planifiés."""
    query = select(ScheduledReport)
    if enabled_only:
        query = query.where(ScheduledReport.enabled == True)
    query = query.order_by(ScheduledReport.name)

    result = await db.execute(query)
    reports = result.scalars().all()

    return [
        ScheduledReportResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            enabled=r.enabled,
            report_type=r.report_type.value if r.report_type else None,
            report_format=r.report_format.value if r.report_format else None,
            frequency=r.frequency.value if r.frequency else None,
            schedule_hour=r.schedule_hour,
            schedule_day=r.schedule_day,
            host_filter=r.host_filter,
            project_filter=r.project_filter,
            include_offline=r.include_offline,
            destination_type=r.destination_type,
            destination_config=r.destination_config or {},
            last_run_at=r.last_run_at,
            last_run_status=r.last_run_status,
            next_run_at=r.next_run_at,
            runs_count=r.runs_count,
            success_count=r.success_count,
            error_count=r.error_count,
            created_at=r.created_at,
        )
        for r in reports
    ]


@router.post("/scheduled", response_model=ScheduledReportResponse)
async def create_scheduled_report(
    data: ScheduledReportCreate,
    db: AsyncSession = Depends(get_db),
):
    """Crée un nouveau rapport planifié."""
    report_id = str(uuid.uuid4())
    next_run = calculate_next_run(data.frequency, data.schedule_hour, data.schedule_day)

    report = ScheduledReport(
        id=report_id,
        name=data.name,
        description=data.description,
        report_type=data.report_type,
        report_format=data.report_format,
        frequency=data.frequency,
        schedule_hour=data.schedule_hour,
        schedule_day=data.schedule_day,
        host_filter=data.host_filter,
        project_filter=data.project_filter,
        include_offline=data.include_offline,
        destination_type=data.destination_type,
        destination_config=data.destination_config.model_dump() if data.destination_config else {},
        next_run_at=next_run,
        enabled=True,
    )

    db.add(report)
    await db.commit()
    await db.refresh(report)

    return ScheduledReportResponse(
        id=report.id,
        name=report.name,
        description=report.description,
        enabled=report.enabled,
        report_type=report.report_type.value,
        report_format=report.report_format.value,
        frequency=report.frequency.value,
        schedule_hour=report.schedule_hour,
        schedule_day=report.schedule_day,
        host_filter=report.host_filter,
        project_filter=report.project_filter,
        include_offline=report.include_offline,
        destination_type=report.destination_type,
        destination_config=report.destination_config or {},
        last_run_at=report.last_run_at,
        last_run_status=report.last_run_status,
        next_run_at=report.next_run_at,
        runs_count=report.runs_count,
        success_count=report.success_count,
        error_count=report.error_count,
        created_at=report.created_at,
    )


@router.get("/scheduled/{report_id}", response_model=ScheduledReportResponse)
async def get_scheduled_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Récupère un rapport planifié par son ID."""
    result = await db.execute(
        select(ScheduledReport).where(ScheduledReport.id == report_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return ScheduledReportResponse(
        id=report.id,
        name=report.name,
        description=report.description,
        enabled=report.enabled,
        report_type=report.report_type.value,
        report_format=report.report_format.value,
        frequency=report.frequency.value,
        schedule_hour=report.schedule_hour,
        schedule_day=report.schedule_day,
        host_filter=report.host_filter,
        project_filter=report.project_filter,
        include_offline=report.include_offline,
        destination_type=report.destination_type,
        destination_config=report.destination_config or {},
        last_run_at=report.last_run_at,
        last_run_status=report.last_run_status,
        next_run_at=report.next_run_at,
        runs_count=report.runs_count,
        success_count=report.success_count,
        error_count=report.error_count,
        created_at=report.created_at,
    )


@router.put("/scheduled/{report_id}", response_model=ScheduledReportResponse)
async def update_scheduled_report(
    report_id: str,
    data: ScheduledReportUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Met à jour un rapport planifié."""
    result = await db.execute(
        select(ScheduledReport).where(ScheduledReport.id == report_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field == "destination_config" and value is not None:
            value = value.model_dump() if hasattr(value, "model_dump") else value
        setattr(report, field, value)

    # Recalculer next_run si la planification change
    if any(f in update_data for f in ["frequency", "schedule_hour", "schedule_day"]):
        report.next_run_at = calculate_next_run(
            report.frequency,
            report.schedule_hour,
            report.schedule_day
        )

    await db.commit()
    await db.refresh(report)

    return ScheduledReportResponse(
        id=report.id,
        name=report.name,
        description=report.description,
        enabled=report.enabled,
        report_type=report.report_type.value,
        report_format=report.report_format.value,
        frequency=report.frequency.value,
        schedule_hour=report.schedule_hour,
        schedule_day=report.schedule_day,
        host_filter=report.host_filter,
        project_filter=report.project_filter,
        include_offline=report.include_offline,
        destination_type=report.destination_type,
        destination_config=report.destination_config or {},
        last_run_at=report.last_run_at,
        last_run_status=report.last_run_status,
        next_run_at=report.next_run_at,
        runs_count=report.runs_count,
        success_count=report.success_count,
        error_count=report.error_count,
        created_at=report.created_at,
    )


@router.delete("/scheduled/{report_id}")
async def delete_scheduled_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Supprime un rapport planifié."""
    result = await db.execute(
        select(ScheduledReport).where(ScheduledReport.id == report_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    await db.delete(report)
    await db.commit()

    return {"status": "deleted", "id": report_id}


@router.post("/scheduled/{report_id}/toggle")
async def toggle_scheduled_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Active/désactive un rapport planifié."""
    result = await db.execute(
        select(ScheduledReport).where(ScheduledReport.id == report_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.enabled = not report.enabled
    if report.enabled:
        # Recalculer next_run si on réactive
        report.next_run_at = calculate_next_run(
            report.frequency,
            report.schedule_hour,
            report.schedule_day
        )

    await db.commit()

    return {"status": "toggled", "enabled": report.enabled}


@router.post("/scheduled/{report_id}/run")
async def run_report_now(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Exécute un rapport immédiatement (manuellement)."""
    result = await db.execute(
        select(ScheduledReport).where(ScheduledReport.id == report_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Créer une entrée d'historique
    history = ReportHistory(
        report_id=report_id,
        started_at=datetime.utcnow(),
        status="running",
    )
    db.add(history)
    await db.commit()
    await db.refresh(history)

    # TODO: Lancer la génération du rapport en background
    # Pour l'instant, on simule une exécution réussie

    return {
        "status": "started",
        "history_id": history.id,
        "message": "Report generation started"
    }


@router.get("/scheduled/{report_id}/history", response_model=List[ReportHistoryResponse])
async def get_report_history(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """Récupère l'historique d'exécution d'un rapport."""
    result = await db.execute(
        select(ReportHistory)
        .where(ReportHistory.report_id == report_id)
        .order_by(ReportHistory.started_at.desc())
        .limit(limit)
    )
    history = result.scalars().all()

    return [
        ReportHistoryResponse(
            id=h.id,
            report_id=h.report_id,
            started_at=h.started_at,
            completed_at=h.completed_at,
            status=h.status,
            error_message=h.error_message,
            file_path=h.file_path,
            file_size=h.file_size,
            stats=h.stats or {},
        )
        for h in history
    ]


@router.get("/types")
async def get_report_types():
    """Liste les types de rapports disponibles."""
    return {
        "types": [
            {"value": t.value, "label": t.value.replace("_", " ").title()}
            for t in ReportType
        ],
        "formats": [
            {"value": f.value, "label": f.value.upper()}
            for f in ReportFormat
        ],
        "frequencies": [
            {"value": f.value, "label": f.value.title()}
            for f in ReportFrequency
        ],
    }
