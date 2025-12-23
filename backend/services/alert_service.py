"""Service de gestion des alertes."""

import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Host,
    Container,
    AlertRule,
    AlertRuleType,
    Alert,
    AlertStatus,
    AlertSeverity,
    AlertChannel,
    ContainerStatusEnum,
    HealthStatusEnum,
)
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class AlertService:
    """Service de gestion des alertes."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_service = NotificationService()

    # =========================================================================
    # CRUD AlertChannel
    # =========================================================================

    async def get_channels(self) -> list[AlertChannel]:
        """Récupère tous les canaux."""
        result = await self.db.execute(select(AlertChannel))
        return list(result.scalars().all())

    async def get_channel(self, channel_id: str) -> Optional[AlertChannel]:
        """Récupère un canal par ID."""
        return await self.db.get(AlertChannel, channel_id)

    async def create_channel(self, data: dict) -> AlertChannel:
        """Crée un nouveau canal."""
        channel = AlertChannel(
            id=str(uuid.uuid4()),
            name=data["name"],
            channel_type=data["channel_type"],
            enabled=data.get("enabled", True),
            config=data.get("config", {}),
            severity_filter=data.get("severity_filter", []),
            rule_type_filter=data.get("rule_type_filter", []),
        )
        self.db.add(channel)
        await self.db.commit()
        await self.db.refresh(channel)
        logger.info(f"Canal créé: {channel.name} ({channel.channel_type})")
        return channel

    async def update_channel(self, channel_id: str, data: dict) -> Optional[AlertChannel]:
        """Met à jour un canal."""
        channel = await self.get_channel(channel_id)
        if not channel:
            return None

        for key, value in data.items():
            if hasattr(channel, key):
                setattr(channel, key, value)

        await self.db.commit()
        await self.db.refresh(channel)
        logger.info(f"Canal mis à jour: {channel.name}")
        return channel

    async def delete_channel(self, channel_id: str) -> bool:
        """Supprime un canal."""
        channel = await self.get_channel(channel_id)
        if not channel:
            return False

        await self.db.delete(channel)
        await self.db.commit()
        logger.info(f"Canal supprimé: {channel.name}")
        return True

    async def test_channel(self, channel_id: str) -> tuple[bool, Optional[str]]:
        """Teste un canal."""
        channel = await self.get_channel(channel_id)
        if not channel:
            return False, "Canal non trouvé"

        success, error = await self.notification_service.test_channel(channel)

        # Mettre à jour last_error
        if not success:
            channel.last_error = error
        else:
            channel.last_error = None
            channel.last_used_at = datetime.utcnow()

        await self.db.commit()
        return success, error

    # =========================================================================
    # CRUD AlertRule
    # =========================================================================

    async def get_rules(self) -> list[AlertRule]:
        """Récupère toutes les règles."""
        result = await self.db.execute(select(AlertRule))
        return list(result.scalars().all())

    async def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Récupère une règle par ID."""
        return await self.db.get(AlertRule, rule_id)

    async def create_rule(self, data: dict) -> AlertRule:
        """Crée une nouvelle règle."""
        rule = AlertRule(
            id=str(uuid.uuid4()),
            name=data["name"],
            description=data.get("description"),
            rule_type=data["rule_type"],
            severity=data.get("severity", AlertSeverity.WARNING),
            enabled=data.get("enabled", True),
            config=data.get("config", {}),
            host_filter=data.get("host_filter"),
            container_filter=data.get("container_filter"),
            project_filter=data.get("project_filter"),
            cooldown_minutes=data.get("cooldown_minutes", 15),
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        logger.info(f"Règle créée: {rule.name} ({rule.rule_type})")
        return rule

    async def update_rule(self, rule_id: str, data: dict) -> Optional[AlertRule]:
        """Met à jour une règle."""
        rule = await self.get_rule(rule_id)
        if not rule:
            return None

        for key, value in data.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        await self.db.commit()
        await self.db.refresh(rule)
        logger.info(f"Règle mise à jour: {rule.name}")
        return rule

    async def delete_rule(self, rule_id: str) -> bool:
        """Supprime une règle."""
        rule = await self.get_rule(rule_id)
        if not rule:
            return False

        await self.db.delete(rule)
        await self.db.commit()
        logger.info(f"Règle supprimée: {rule.name}")
        return True

    # =========================================================================
    # CRUD Alert
    # =========================================================================

    async def get_alerts(
        self,
        status: Optional[AlertStatus] = None,
        severity: Optional[AlertSeverity] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Alert]:
        """Récupère les alertes avec filtres."""
        query = select(Alert)

        conditions = []
        if status:
            conditions.append(Alert.status == status)
        if severity:
            conditions.append(Alert.severity == severity)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(Alert.triggered_at.desc()).offset(offset).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Récupère une alerte par ID."""
        return await self.db.get(Alert, alert_id)

    async def get_active_alerts_count(self) -> dict:
        """Compte les alertes actives par sévérité."""
        result = await self.db.execute(
            select(Alert).where(Alert.status == AlertStatus.ACTIVE)
        )
        alerts = result.scalars().all()

        counts = {"total": 0, "info": 0, "warning": 0, "critical": 0}
        for alert in alerts:
            counts["total"] += 1
            counts[alert.severity.value] += 1

        return counts

    async def acknowledge_alert(self, alert_id: str, user_id: Optional[str] = None) -> Optional[Alert]:
        """Acquitte une alerte."""
        alert = await self.get_alert(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = user_id

        await self.db.commit()
        await self.db.refresh(alert)
        logger.info(f"Alerte acquittée: {alert.id}")
        return alert

    async def resolve_alert(self, alert_id: str) -> Optional[Alert]:
        """Résout une alerte."""
        alert = await self.get_alert(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(alert)
        logger.info(f"Alerte résolue: {alert.id}")
        return alert

    async def delete_alert(self, alert_id: str) -> bool:
        """Supprime une alerte."""
        alert = await self.get_alert(alert_id)
        if not alert:
            return False

        await self.db.delete(alert)
        await self.db.commit()
        return True

    async def delete_old_alerts(self, days: int = 30) -> int:
        """Supprime les alertes résolues plus anciennes que X jours."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        result = await self.db.execute(
            select(Alert).where(
                and_(
                    Alert.status == AlertStatus.RESOLVED,
                    Alert.resolved_at < cutoff,
                )
            )
        )
        old_alerts = result.scalars().all()

        count = len(old_alerts)
        for alert in old_alerts:
            await self.db.delete(alert)

        await self.db.commit()
        logger.info(f"Supprimé {count} alertes résolues de plus de {days} jours")
        return count

    # =========================================================================
    # Evaluation des règles
    # =========================================================================

    async def evaluate_all_rules(self) -> list[Alert]:
        """Évalue toutes les règles actives et génère les alertes."""
        result = await self.db.execute(
            select(AlertRule).where(AlertRule.enabled == True)
        )
        rules = result.scalars().all()

        new_alerts = []
        for rule in rules:
            alerts = await self._evaluate_rule(rule)
            new_alerts.extend(alerts)

        return new_alerts

    async def _evaluate_rule(self, rule: AlertRule) -> list[Alert]:
        """Évalue une règle spécifique."""
        if rule.rule_type == AlertRuleType.HOST_OFFLINE:
            return await self._evaluate_host_offline(rule)
        elif rule.rule_type == AlertRuleType.CONTAINER_STOPPED:
            return await self._evaluate_container_stopped(rule)
        elif rule.rule_type == AlertRuleType.CONTAINER_UNHEALTHY:
            return await self._evaluate_container_unhealthy(rule)
        else:
            return []

    async def _evaluate_host_offline(self, rule: AlertRule) -> list[Alert]:
        """Évalue la règle host_offline."""
        timeout_minutes = rule.config.get("timeout_minutes", 5)
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)

        # Trouver les hosts offline
        result = await self.db.execute(
            select(Host).where(Host.last_seen < cutoff)
        )
        offline_hosts = result.scalars().all()

        new_alerts = []
        for host in offline_hosts:
            # Vérifier le filtre
            if rule.host_filter and not self._matches_pattern(host.hostname, rule.host_filter):
                continue

            # Vérifier le cooldown
            if await self._is_in_cooldown(rule, host_id=host.id):
                continue

            # Vérifier s'il y a déjà une alerte active
            existing = await self._get_active_alert(rule.id, host_id=host.id)
            if existing:
                continue

            # Créer l'alerte
            alert = await self._create_alert(
                rule=rule,
                title=f"Host offline: {host.hostname}",
                message=f"Le host {host.hostname} n'a pas été vu depuis {timeout_minutes} minutes. Dernière activité: {host.last_seen.strftime('%Y-%m-%d %H:%M:%S') if host.last_seen else 'jamais'}",
                host_id=host.id,
                host_name=host.hostname,
            )
            new_alerts.append(alert)

        # Résoudre les alertes pour les hosts revenus online
        await self._resolve_old_alerts(rule, offline_host_ids=[h.id for h in offline_hosts])

        return new_alerts

    async def _evaluate_container_stopped(self, rule: AlertRule) -> list[Alert]:
        """Évalue la règle container_stopped."""
        # Trouver les containers arrêtés
        result = await self.db.execute(
            select(Container).where(
                Container.status.in_([
                    ContainerStatusEnum.STOPPED,
                    ContainerStatusEnum.EXITED,
                    ContainerStatusEnum.DEAD,
                ])
            )
        )
        stopped_containers = result.scalars().all()

        new_alerts = []
        for container in stopped_containers:
            # Récupérer le host
            host = await self.db.get(Host, container.host_id)
            if not host:
                continue

            # Vérifier les filtres
            if rule.host_filter and not self._matches_pattern(host.hostname, rule.host_filter):
                continue
            if rule.container_filter and not self._matches_pattern(container.name, rule.container_filter):
                continue
            if rule.project_filter and container.compose_project:
                if not self._matches_pattern(container.compose_project, rule.project_filter):
                    continue

            # Vérifier les exclusions
            exclude_patterns = rule.config.get("exclude", [])
            if any(self._matches_pattern(container.name, p) for p in exclude_patterns):
                continue

            # Vérifier le cooldown
            if await self._is_in_cooldown(rule, container_id=container.id):
                continue

            # Vérifier s'il y a déjà une alerte active
            existing = await self._get_active_alert(rule.id, container_id=container.id)
            if existing:
                continue

            # Créer l'alerte
            alert = await self._create_alert(
                rule=rule,
                title=f"Container arrêté: {container.name}",
                message=f"Le container {container.name} sur {host.hostname} est arrêté (status: {container.status.value})",
                host_id=host.id,
                host_name=host.hostname,
                container_id=container.id,
                container_name=container.name,
                context={"compose_project": container.compose_project},
            )
            new_alerts.append(alert)

        # Résoudre les alertes pour les containers redémarrés
        await self._resolve_container_alerts(rule, stopped_container_ids=[c.id for c in stopped_containers])

        return new_alerts

    async def _evaluate_container_unhealthy(self, rule: AlertRule) -> list[Alert]:
        """Évalue la règle container_unhealthy."""
        # Trouver les containers unhealthy
        result = await self.db.execute(
            select(Container).where(Container.health == HealthStatusEnum.UNHEALTHY)
        )
        unhealthy_containers = result.scalars().all()

        new_alerts = []
        for container in unhealthy_containers:
            host = await self.db.get(Host, container.host_id)
            if not host:
                continue

            # Vérifier les filtres
            if rule.host_filter and not self._matches_pattern(host.hostname, rule.host_filter):
                continue
            if rule.container_filter and not self._matches_pattern(container.name, rule.container_filter):
                continue

            # Vérifier le cooldown
            if await self._is_in_cooldown(rule, container_id=container.id):
                continue

            # Vérifier s'il y a déjà une alerte active
            existing = await self._get_active_alert(rule.id, container_id=container.id)
            if existing:
                continue

            # Créer l'alerte
            alert = await self._create_alert(
                rule=rule,
                title=f"Container unhealthy: {container.name}",
                message=f"Le container {container.name} sur {host.hostname} est en état unhealthy",
                host_id=host.id,
                host_name=host.hostname,
                container_id=container.id,
                container_name=container.name,
            )
            new_alerts.append(alert)

        # Résoudre les alertes pour les containers redevenus healthy
        await self._resolve_container_alerts(rule, stopped_container_ids=[c.id for c in unhealthy_containers])

        return new_alerts

    # =========================================================================
    # Helpers
    # =========================================================================

    def _matches_pattern(self, value: str, pattern: str) -> bool:
        """Vérifie si une valeur correspond à un pattern (regex ou glob)."""
        if not pattern:
            return True

        # Convertir glob en regex si nécessaire
        if "*" in pattern and not pattern.startswith("^"):
            pattern = pattern.replace("*", ".*")
            pattern = f"^{pattern}$"

        try:
            return bool(re.match(pattern, value, re.IGNORECASE))
        except re.error:
            return value == pattern

    async def _is_in_cooldown(
        self,
        rule: AlertRule,
        host_id: Optional[str] = None,
        container_id: Optional[str] = None,
    ) -> bool:
        """Vérifie si une alerte récente existe (cooldown)."""
        cutoff = datetime.utcnow() - timedelta(minutes=rule.cooldown_minutes)

        conditions = [
            Alert.rule_id == rule.id,
            Alert.triggered_at > cutoff,
        ]

        if host_id:
            conditions.append(Alert.host_id == host_id)
        if container_id:
            conditions.append(Alert.container_id == container_id)

        result = await self.db.execute(
            select(Alert).where(and_(*conditions)).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _get_active_alert(
        self,
        rule_id: str,
        host_id: Optional[str] = None,
        container_id: Optional[str] = None,
    ) -> Optional[Alert]:
        """Récupère une alerte active pour une ressource."""
        conditions = [
            Alert.rule_id == rule_id,
            Alert.status == AlertStatus.ACTIVE,
        ]

        if host_id:
            conditions.append(Alert.host_id == host_id)
        if container_id:
            conditions.append(Alert.container_id == container_id)

        result = await self.db.execute(
            select(Alert).where(and_(*conditions)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _create_alert(
        self,
        rule: AlertRule,
        title: str,
        message: str,
        host_id: Optional[str] = None,
        host_name: Optional[str] = None,
        container_id: Optional[str] = None,
        container_name: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> Alert:
        """Crée une nouvelle alerte et envoie les notifications."""
        alert = Alert(
            id=str(uuid.uuid4()),
            rule_id=rule.id,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            title=title,
            message=message,
            host_id=host_id,
            host_name=host_name,
            container_id=container_id,
            container_name=container_name,
            context=context or {},
            triggered_at=datetime.utcnow(),
        )
        self.db.add(alert)
        await self.db.commit()
        await self.db.refresh(alert)

        logger.warning(f"Alerte créée: [{rule.severity.value}] {title}")

        # Envoyer les notifications
        await self._send_notifications(alert)

        return alert

    async def _send_notifications(self, alert: Alert):
        """Envoie les notifications pour une alerte."""
        # Récupérer les canaux actifs
        result = await self.db.execute(
            select(AlertChannel).where(AlertChannel.enabled == True)
        )
        channels = result.scalars().all()

        notifications_sent = []

        for channel in channels:
            # Vérifier les filtres de sévérité
            if channel.severity_filter and alert.severity.value not in channel.severity_filter:
                continue

            # Vérifier les filtres de type de règle
            if channel.rule_type_filter:
                rule = await self.get_rule(alert.rule_id)
                if rule and rule.rule_type.value not in channel.rule_type_filter:
                    continue

            # Envoyer
            success, error = await self.notification_service.send_notification(channel, alert)

            notification_record = {
                "channel_id": channel.id,
                "channel_name": channel.name,
                "sent_at": datetime.utcnow().isoformat(),
                "success": success,
                "error": error,
            }
            notifications_sent.append(notification_record)

            # Mettre à jour le canal
            channel.last_used_at = datetime.utcnow()
            if not success:
                channel.last_error = error

            if success:
                logger.info(f"Notification envoyée via {channel.name}")
            else:
                logger.error(f"Erreur notification {channel.name}: {error}")

        # Mettre à jour l'alerte avec les notifications envoyées
        alert.notifications_sent = notifications_sent
        await self.db.commit()

    async def _resolve_old_alerts(
        self,
        rule: AlertRule,
        offline_host_ids: list[str],
    ):
        """Résout les alertes pour les hosts revenus online."""
        result = await self.db.execute(
            select(Alert).where(
                and_(
                    Alert.rule_id == rule.id,
                    Alert.status == AlertStatus.ACTIVE,
                    Alert.host_id.notin_(offline_host_ids) if offline_host_ids else True,
                )
            )
        )
        alerts_to_resolve = result.scalars().all()

        for alert in alerts_to_resolve:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.utcnow()
            logger.info(f"Alerte auto-résolue: {alert.title}")

        await self.db.commit()

    async def _resolve_container_alerts(
        self,
        rule: AlertRule,
        stopped_container_ids: list[str],
    ):
        """Résout les alertes pour les containers redémarrés."""
        if not stopped_container_ids:
            # Tous les containers sont OK, résoudre toutes les alertes actives de cette règle
            result = await self.db.execute(
                select(Alert).where(
                    and_(
                        Alert.rule_id == rule.id,
                        Alert.status == AlertStatus.ACTIVE,
                    )
                )
            )
        else:
            result = await self.db.execute(
                select(Alert).where(
                    and_(
                        Alert.rule_id == rule.id,
                        Alert.status == AlertStatus.ACTIVE,
                        Alert.container_id.notin_(stopped_container_ids),
                    )
                )
            )

        alerts_to_resolve = result.scalars().all()

        for alert in alerts_to_resolve:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.utcnow()
            logger.info(f"Alerte auto-résolue: {alert.title}")

        await self.db.commit()
