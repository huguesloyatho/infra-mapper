"""Service de notification multi-canal."""

import logging
import aiohttp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional

from db.models import AlertChannel, AlertChannelType, Alert, AlertSeverity, AlertStatus

logger = logging.getLogger(__name__)


class NotificationService:
    """Service pour envoyer des notifications via différents canaux."""

    # Emojis par sévérité
    SEVERITY_EMOJI = {
        AlertSeverity.INFO: "ℹ️",
        AlertSeverity.WARNING: "⚠️",
        AlertSeverity.CRITICAL: "🚨",
    }

    SEVERITY_COLOR = {
        AlertSeverity.INFO: "#3b82f6",      # Blue
        AlertSeverity.WARNING: "#f59e0b",   # Orange
        AlertSeverity.CRITICAL: "#ef4444",  # Red
    }

    async def send_notification(
        self,
        channel: AlertChannel,
        alert: Alert,
    ) -> tuple[bool, Optional[str]]:
        """
        Envoie une notification via un canal.

        Returns:
            (success, error_message)
        """
        try:
            if channel.channel_type == AlertChannelType.SLACK:
                return await self._send_slack(channel, alert)
            elif channel.channel_type == AlertChannelType.DISCORD:
                return await self._send_discord(channel, alert)
            elif channel.channel_type == AlertChannelType.TELEGRAM:
                return await self._send_telegram(channel, alert)
            elif channel.channel_type == AlertChannelType.EMAIL:
                return await self._send_email(channel, alert)
            elif channel.channel_type == AlertChannelType.NTFY:
                return await self._send_ntfy(channel, alert)
            elif channel.channel_type == AlertChannelType.WEBHOOK:
                return await self._send_webhook(channel, alert)
            else:
                return False, f"Type de canal non supporté: {channel.channel_type}"
        except Exception as e:
            logger.error(f"Erreur envoi notification {channel.name}: {e}")
            return False, str(e)

    async def _send_slack(
        self,
        channel: AlertChannel,
        alert: Alert,
    ) -> tuple[bool, Optional[str]]:
        """Envoie une notification Slack."""
        webhook_url = channel.config.get("webhook_url")
        if not webhook_url:
            return False, "webhook_url manquant dans la config"

        emoji = self.SEVERITY_EMOJI.get(alert.severity, "📢")
        color = self.SEVERITY_COLOR.get(alert.severity, "#6b7280")

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"{emoji} {alert.title}",
                                "emoji": True,
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": alert.message,
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Sévérité:* {alert.severity.value} | *Host:* {alert.host_name or 'N/A'} | *Container:* {alert.container_name or 'N/A'}",
                                },
                            ],
                        },
                    ],
                }
            ]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status == 200:
                    return True, None
                else:
                    text = await resp.text()
                    return False, f"Slack error {resp.status}: {text}"

    async def _send_discord(
        self,
        channel: AlertChannel,
        alert: Alert,
    ) -> tuple[bool, Optional[str]]:
        """Envoie une notification Discord."""
        webhook_url = channel.config.get("webhook_url")
        if not webhook_url:
            return False, "webhook_url manquant dans la config"

        emoji = self.SEVERITY_EMOJI.get(alert.severity, "📢")
        color = int(self.SEVERITY_COLOR.get(alert.severity, "#6b7280").lstrip("#"), 16)

        payload = {
            "embeds": [
                {
                    "title": f"{emoji} {alert.title}",
                    "description": alert.message,
                    "color": color,
                    "fields": [
                        {
                            "name": "Sévérité",
                            "value": alert.severity.value,
                            "inline": True,
                        },
                        {
                            "name": "Host",
                            "value": alert.host_name or "N/A",
                            "inline": True,
                        },
                        {
                            "name": "Container",
                            "value": alert.container_name or "N/A",
                            "inline": True,
                        },
                    ],
                    "timestamp": alert.triggered_at.isoformat() if alert.triggered_at else datetime.utcnow().isoformat(),
                    "footer": {
                        "text": "Infra-Mapper Alerting",
                    },
                }
            ]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status in (200, 204):
                    return True, None
                else:
                    text = await resp.text()
                    return False, f"Discord error {resp.status}: {text}"

    async def _send_telegram(
        self,
        channel: AlertChannel,
        alert: Alert,
    ) -> tuple[bool, Optional[str]]:
        """Envoie une notification Telegram."""
        bot_token = channel.config.get("bot_token")
        chat_id = channel.config.get("chat_id")

        if not bot_token or not chat_id:
            return False, "bot_token ou chat_id manquant dans la config"

        emoji = self.SEVERITY_EMOJI.get(alert.severity, "📢")

        # Format message en HTML
        message = f"""<b>{emoji} {alert.title}</b>

{alert.message}

<b>Sévérité:</b> {alert.severity.value}
<b>Host:</b> {alert.host_name or 'N/A'}
<b>Container:</b> {alert.container_name or 'N/A'}
<b>Date:</b> {alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S') if alert.triggered_at else 'N/A'}"""

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    return True, None
                else:
                    data = await resp.json()
                    return False, f"Telegram error: {data.get('description', 'Unknown error')}"

    async def _send_email(
        self,
        channel: AlertChannel,
        alert: Alert,
    ) -> tuple[bool, Optional[str]]:
        """Envoie une notification par email."""
        config = channel.config
        smtp_host = config.get("smtp_host")
        smtp_port = config.get("smtp_port", 587)
        smtp_user = config.get("smtp_user")
        smtp_password = config.get("smtp_password")
        from_addr = config.get("from")
        to_addrs = config.get("to", [])
        use_tls = config.get("use_tls", True)

        if not smtp_host or not from_addr or not to_addrs:
            return False, "Configuration SMTP incomplète"

        emoji = self.SEVERITY_EMOJI.get(alert.severity, "📢")

        # Créer le message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{emoji} [{alert.severity.value.upper()}] {alert.title}"
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)

        # Version texte
        text_content = f"""{alert.title}

{alert.message}

Sévérité: {alert.severity.value}
Host: {alert.host_name or 'N/A'}
Container: {alert.container_name or 'N/A'}
Date: {alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S') if alert.triggered_at else 'N/A'}

---
Infra-Mapper Alerting"""

        # Version HTML
        color = self.SEVERITY_COLOR.get(alert.severity, "#6b7280")
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .alert-box {{ border-left: 4px solid {color}; padding: 16px; background: #f9fafb; margin: 16px 0; }}
        .title {{ font-size: 18px; font-weight: bold; margin-bottom: 8px; }}
        .message {{ margin: 16px 0; }}
        .meta {{ color: #6b7280; font-size: 14px; }}
        .meta span {{ margin-right: 16px; }}
    </style>
</head>
<body>
    <div class="alert-box">
        <div class="title">{emoji} {alert.title}</div>
        <div class="message">{alert.message}</div>
        <div class="meta">
            <span><strong>Sévérité:</strong> {alert.severity.value}</span>
            <span><strong>Host:</strong> {alert.host_name or 'N/A'}</span>
            <span><strong>Container:</strong> {alert.container_name or 'N/A'}</span>
        </div>
    </div>
    <p style="color: #9ca3af; font-size: 12px;">Infra-Mapper Alerting</p>
</body>
</html>"""

        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        try:
            if use_tls:
                server = smtplib.SMTP(smtp_host, smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(smtp_host, smtp_port)

            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)

            server.sendmail(from_addr, to_addrs, msg.as_string())
            server.quit()
            return True, None
        except Exception as e:
            return False, f"SMTP error: {str(e)}"

    async def _send_ntfy(
        self,
        channel: AlertChannel,
        alert: Alert,
    ) -> tuple[bool, Optional[str]]:
        """Envoie une notification via ntfy.sh."""
        # Support both 'server' and 'server_url' for compatibility
        server = channel.config.get("server") or channel.config.get("server_url", "https://ntfy.sh")
        topic = channel.config.get("topic")
        token = channel.config.get("token")  # Optionnel pour auth

        if not topic:
            return False, "topic manquant dans la config"

        emoji = self.SEVERITY_EMOJI.get(alert.severity, "📢")

        # Priorité ntfy basée sur la sévérité
        priority_map = {
            AlertSeverity.INFO: "default",
            AlertSeverity.WARNING: "high",
            AlertSeverity.CRITICAL: "urgent",
        }

        headers = {
            "Title": f"{emoji} {alert.title}",
            "Priority": priority_map.get(alert.severity, "default"),
            "Tags": f"{alert.severity.value},infra-mapper",
        }

        if token:
            headers["Authorization"] = f"Bearer {token}"

        if alert.host_name:
            headers["Tags"] += f",{alert.host_name}"

        url = f"{server.rstrip('/')}/{topic}"
        message = f"{alert.message}\n\nHost: {alert.host_name or 'N/A'}\nContainer: {alert.container_name or 'N/A'}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=message, headers=headers) as resp:
                if resp.status == 200:
                    return True, None
                else:
                    text = await resp.text()
                    return False, f"ntfy error {resp.status}: {text}"

    async def _send_webhook(
        self,
        channel: AlertChannel,
        alert: Alert,
    ) -> tuple[bool, Optional[str]]:
        """Envoie une notification via webhook générique."""
        url = channel.config.get("url")
        method = channel.config.get("method", "POST").upper()
        custom_headers = channel.config.get("headers", {})
        include_context = channel.config.get("include_context", True)

        if not url:
            return False, "url manquant dans la config"

        # Payload standard
        payload = {
            "alert_id": alert.id,
            "rule_id": alert.rule_id,
            "severity": alert.severity.value,
            "status": alert.status.value,
            "title": alert.title,
            "message": alert.message,
            "host_id": alert.host_id,
            "host_name": alert.host_name,
            "container_id": alert.container_id,
            "container_name": alert.container_name,
            "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        }

        if include_context and alert.context:
            payload["context"] = alert.context

        headers = {"Content-Type": "application/json"}
        headers.update(custom_headers)

        async with aiohttp.ClientSession() as session:
            if method == "POST":
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status in (200, 201, 202, 204):
                        return True, None
                    else:
                        text = await resp.text()
                        return False, f"Webhook error {resp.status}: {text}"
            else:
                return False, f"Méthode HTTP non supportée: {method}"

    async def test_channel(self, channel: AlertChannel) -> tuple[bool, Optional[str]]:
        """Teste un canal de notification."""
        # Créer une alerte de test
        test_alert = Alert(
            id="test-alert",
            rule_id="test-rule",
            severity=AlertSeverity.INFO,
            status=AlertStatus.ACTIVE,
            title="Test de notification",
            message="Ceci est un message de test pour vérifier la configuration du canal de notification.",
            host_name="test-host",
            container_name="test-container",
            triggered_at=datetime.utcnow(),
        )

        return await self.send_notification(channel, test_alert)
