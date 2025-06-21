"""
Mailgun Service - Email automation and management for agents
"""

import base64
import hashlib
import hmac
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Union

import requests

from src.exceptions import ServiceError, SwarmException
from src.services.base_service import BaseService, handle_service_errors

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Represents an email message"""

    to: List[str]
    subject: str
    text_content: str
    html_content: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class EmailTemplate:
    """Represents an email template"""

    name: str
    subject: str
    text_content: str
    html_content: Optional[str] = None
    variables: Optional[List[str]] = None
    description: Optional[str] = None


@dataclass
class EmailDeliveryStatus:
    """Represents email delivery status"""

    message_id: str
    status: str  # queued, sent, delivered, failed, bounced, complained
    timestamp: str
    recipient: str
    reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class MailgunService(BaseService):
    """Service for email automation using Mailgun API"""

    def __init__(
        self,
        api_key: str,
        domain: str,
        webhook_signing_key: str = None,
        base_url: str = "https://api.mailgun.net/v3",
    ):
        super().__init__("Mailgun")
        self.api_key = api_key
        self.domain = domain
        self.webhook_signing_key = webhook_signing_key
        self.base_url = base_url.rstrip("/")
        self.auth = ("api", api_key)

        # Validate configuration
        if not self.api_key:
            raise ServiceError("Mailgun API key is required", error_code="MISSING_API_KEY")

        if not self.domain:
            raise ServiceError("Mailgun domain is required", error_code="MISSING_DOMAIN")

        # Email templates storage
        self.templates = {}
        self._load_default_templates()

        logger.info(f"Mailgun service initialized for domain: {self.domain}")

    def _load_default_templates(self):
        """Load default email templates"""
        self.templates = {
            "welcome": EmailTemplate(
                name="welcome",
                subject="Welcome to Swarm Multi-Agent System",
                text_content="""
Hello {name},

Welcome to the Swarm Multi-Agent System! Your account has been successfully created.

You can now access your personalized AI agents and start collaborating with them to accomplish your tasks.

Best regards,
The Swarm Team
                """.strip(),
                html_content="""
<html>
<body>
<h2>Welcome to Swarm Multi-Agent System</h2>
<p>Hello <strong>{name}</strong>,</p>
<p>Welcome to the Swarm Multi-Agent System! Your account has been successfully created.</p>
<p>You can now access your personalized AI agents and start collaborating with them to accomplish your tasks.</p>
<p>Best regards,<br>The Swarm Team</p>
</body>
</html>
                """.strip(),
                variables=["name"],
                description="Welcome email for new users",
            ),
            "task_completion": EmailTemplate(
                name="task_completion",
                subject="Task Completed: {task_title}",
                text_content="""
Hello {name},

Your task "{task_title}" has been completed successfully by the {agent_name} agent.

Task Details:
- Started: {start_time}
- Completed: {completion_time}
- Duration: {duration}

Summary: {summary}

You can view the full details in your dashboard.

Best regards,
The Swarm Team
                """.strip(),
                variables=[
                    "name",
                    "task_title",
                    "agent_name",
                    "start_time",
                    "completion_time",
                    "duration",
                    "summary",
                ],
                description="Task completion notification",
            ),
            "agent_report": EmailTemplate(
                name="agent_report",
                subject="Daily Agent Report - {date}",
                text_content="""
Hello {name},

Here's your daily agent activity report for {date}:

Agent Activity:
{agent_activity}

Key Accomplishments:
{accomplishments}

Upcoming Tasks:
{upcoming_tasks}

Best regards,
The Swarm Team
                """.strip(),
                variables=["name", "date", "agent_activity", "accomplishments", "upcoming_tasks"],
                description="Daily agent activity report",
            ),
        }

    @handle_service_errors
    def send_email(self, message: EmailMessage, agent_id: str = None) -> Dict[str, Any]:
        """Send an email message"""

        # Validate message
        if not message.to:
            raise ServiceError("Email recipients are required", error_code="MISSING_RECIPIENTS")

        if not message.subject:
            raise ServiceError("Email subject is required", error_code="MISSING_SUBJECT")

        if not message.text_content and not message.html_content:
            raise ServiceError(
                "Email content (text or HTML) is required", error_code="MISSING_CONTENT"
            )

        # Prepare email data
        email_data = {
            "from": f"{message.from_name or 'Swarm Agent'} <{message.from_email or f'noreply@{self.domain}'}>",
            "to": message.to,
            "subject": message.subject,
            "text": message.text_content,
        }

        if message.html_content:
            email_data["html"] = message.html_content

        if message.reply_to:
            email_data["h:Reply-To"] = message.reply_to

        if message.cc:
            email_data["cc"] = message.cc

        if message.bcc:
            email_data["bcc"] = message.bcc

        if message.tags:
            email_data["o:tag"] = message.tags

        # Add metadata
        metadata = message.metadata or {}
        if agent_id:
            metadata["agent_id"] = agent_id
        metadata["sent_at"] = datetime.now(timezone.utc).isoformat()

        for key, value in metadata.items():
            email_data[f"v:{key}"] = str(value)

        try:
            # Send email via Mailgun API
            response = self.post(
                f"{self.base_url}/{self.domain}/messages", auth=self.auth, data=email_data
            )

            if response.status_code == 200:
                result = response.json()
                message_id = result.get("id", "")

                logger.info(f"Email sent successfully: {message_id}")

                return {
                    "success": True,
                    "message_id": message_id,
                    "status": "queued",
                    "recipients": len(message.to),
                    "sent_at": metadata["sent_at"],
                }
            else:
                raise ServiceError(
                    f"Failed to send email: {response.status_code}",
                    error_code="SEND_FAILED",
                    details={"status_code": response.status_code, "response": response.text},
                )

        except requests.exceptions.RequestException as e:
            raise ServiceError(
                f"Network error sending email: {str(e)}",
                error_code="NETWORK_ERROR",
                details={"error": str(e)},
            )

    @handle_service_errors
    def send_template_email(
        self,
        template_name: str,
        recipients: List[str],
        variables: Dict[str, str],
        agent_id: str = None,
    ) -> Dict[str, Any]:
        """Send email using a template"""

        if template_name not in self.templates:
            raise ServiceError(
                f"Template not found: {template_name}",
                error_code="TEMPLATE_NOT_FOUND",
                details={"available_templates": list(self.templates.keys())},
            )

        template = self.templates[template_name]

        # Replace variables in template
        try:
            subject = template.subject.format(**variables)
            text_content = template.text_content.format(**variables)
            html_content = (
                template.html_content.format(**variables) if template.html_content else None
            )
        except KeyError as e:
            raise ServiceError(
                f"Missing template variable: {str(e)}",
                error_code="MISSING_TEMPLATE_VARIABLE",
                details={"missing_variable": str(e), "required_variables": template.variables},
            )

        # Create email message
        message = EmailMessage(
            to=recipients,
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            tags=[f"template:{template_name}"],
            metadata={"template": template_name, **variables},
        )

        return self.send_email(message, agent_id)

    @handle_service_errors
    def compose_ai_email(self, context: Dict[str, Any], agent_id: str) -> EmailMessage:
        """Compose an email using AI based on context"""

        # Extract context information
        recipient = context.get("recipient", "")
        purpose = context.get("purpose", "")
        tone = context.get("tone", "professional")
        key_points = context.get("key_points", [])
        user_name = context.get("user_name", "User")

        if not recipient:
            raise ServiceError(
                "Recipient is required for AI email composition", error_code="MISSING_RECIPIENT"
            )

        if not purpose:
            raise ServiceError(
                "Email purpose is required for AI email composition", error_code="MISSING_PURPOSE"
            )

        # Generate email content based on context
        # This is a simplified version - in production, you'd use the OpenRouter service
        # to generate more sophisticated content

        subject_templates = {
            "professional": f"Re: {purpose}",
            "friendly": f"Quick note about {purpose}",
            "formal": f"Regarding: {purpose}",
            "urgent": f"URGENT: {purpose}",
        }

        greeting_templates = {
            "professional": f"Dear {recipient.split('@')[0].title()},",
            "friendly": f"Hi {recipient.split('@')[0].title()}!",
            "formal": f"Dear Sir/Madam,",
            "urgent": f"Hello {recipient.split('@')[0].title()},",
        }

        closing_templates = {
            "professional": f"Best regards,\n{user_name}",
            "friendly": f"Thanks!\n{user_name}",
            "formal": f"Sincerely,\n{user_name}",
            "urgent": f"Please respond ASAP.\n\nThanks,\n{user_name}",
        }

        # Build email content
        subject = subject_templates.get(tone, subject_templates["professional"])
        greeting = greeting_templates.get(tone, greeting_templates["professional"])
        closing = closing_templates.get(tone, closing_templates["professional"])

        # Build body
        body_parts = [greeting, "", f"I hope this email finds you well."]

        if key_points:
            body_parts.append("")
            body_parts.append("I wanted to reach out regarding the following:")
            for point in key_points:
                body_parts.append(f"• {point}")
        else:
            body_parts.append(f"I wanted to reach out regarding {purpose}.")

        body_parts.extend(["", "Please let me know if you have any questions.", "", closing])

        text_content = "\n".join(body_parts)

        # Create HTML version
        html_content = f"""
<html>
<body>
<p>{greeting.replace(',', '')}</p>
<p>I hope this email finds you well.</p>
"""

        if key_points:
            html_content += "<p>I wanted to reach out regarding the following:</p><ul>"
            for point in key_points:
                html_content += f"<li>{point}</li>"
            html_content += "</ul>"
        else:
            html_content += f"<p>I wanted to reach out regarding {purpose}.</p>"

        html_content += f"""
<p>Please let me know if you have any questions.</p>
<p>{closing.replace(chr(10), '<br>')}</p>
</body>
</html>
        """

        return EmailMessage(
            to=[recipient],
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            tags=[f"ai_composed", f"tone:{tone}", f"agent:{agent_id}"],
            metadata={
                "composed_by": "ai",
                "agent_id": agent_id,
                "purpose": purpose,
                "tone": tone,
                "composed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    @handle_service_errors
    def get_delivery_status(self, message_id: str) -> EmailDeliveryStatus:
        """Get delivery status for a message"""

        try:
            response = self.get(
                f"{self.base_url}/{self.domain}/events",
                auth=self.auth,
                params={"message-id": message_id},
            )

            if response.status_code == 200:
                events = response.json().get("items", [])

                if not events:
                    return EmailDeliveryStatus(
                        message_id=message_id,
                        status="unknown",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        recipient="unknown",
                    )

                # Get the latest event
                latest_event = events[0]

                return EmailDeliveryStatus(
                    message_id=message_id,
                    status=latest_event.get("event", "unknown"),
                    timestamp=latest_event.get("timestamp", ""),
                    recipient=latest_event.get("recipient", ""),
                    reason=latest_event.get("reason"),
                    details=latest_event,
                )
            else:
                raise ServiceError(
                    f"Failed to get delivery status: {response.status_code}",
                    error_code="STATUS_FAILED",
                    details={"status_code": response.status_code},
                )

        except requests.exceptions.RequestException as e:
            raise ServiceError(
                f"Network error getting delivery status: {str(e)}",
                error_code="NETWORK_ERROR",
                details={"error": str(e)},
            )

    @handle_service_errors
    def verify_webhook(self, timestamp: str, token: str, signature: str) -> bool:
        """Verify Mailgun webhook signature"""

        if not self.webhook_signing_key:
            logger.warning("Webhook signing key not configured")
            return False

        try:
            # Create HMAC signature
            message = f"{timestamp}{token}".encode("utf-8")
            expected_signature = hmac.new(
                self.webhook_signing_key.encode("utf-8"), message, hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False

    @handle_service_errors
    def process_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming webhook from Mailgun"""

        event_type = webhook_data.get("event-data", {}).get("event")
        message_id = (
            webhook_data.get("event-data", {})
            .get("message", {})
            .get("headers", {})
            .get("message-id")
        )
        recipient = webhook_data.get("event-data", {}).get("recipient")
        timestamp = webhook_data.get("event-data", {}).get("timestamp")

        logger.info(f"Processing webhook: {event_type} for message {message_id}")

        # Create delivery status
        status = EmailDeliveryStatus(
            message_id=message_id or "unknown",
            status=event_type or "unknown",
            timestamp=str(timestamp) if timestamp else datetime.now(timezone.utc).isoformat(),
            recipient=recipient or "unknown",
            details=webhook_data.get("event-data", {}),
        )

        # Handle different event types
        if event_type == "delivered":
            logger.info(f"Email delivered successfully to {recipient}")
        elif event_type == "bounced":
            reason = (
                webhook_data.get("event-data", {}).get("delivery-status", {}).get("description")
            )
            logger.warning(f"Email bounced for {recipient}: {reason}")
            status.reason = reason
        elif event_type == "complained":
            logger.warning(f"Spam complaint from {recipient}")
        elif event_type == "failed":
            reason = (
                webhook_data.get("event-data", {}).get("delivery-status", {}).get("description")
            )
            logger.error(f"Email failed for {recipient}: {reason}")
            status.reason = reason

        return {"processed": True, "event_type": event_type, "status": asdict(status)}

    @handle_service_errors
    def get_domain_stats(self) -> Dict[str, Any]:
        """Get domain statistics"""

        try:
            response = self.get(
                f"{self.base_url}/{self.domain}/stats/total",
                auth=self.auth,
                params={"event": ["sent", "delivered", "failed", "bounced"]},
            )

            if response.status_code == 200:
                stats = response.json().get("stats", [])

                # Process stats
                total_stats = {
                    "sent": 0,
                    "delivered": 0,
                    "failed": 0,
                    "bounced": 0,
                    "delivery_rate": 0.0,
                    "bounce_rate": 0.0,
                }

                for stat in stats:
                    event = stat.get("event")
                    count = stat.get("total_count", 0)
                    if event in total_stats:
                        total_stats[event] = count

                # Calculate rates
                if total_stats["sent"] > 0:
                    total_stats["delivery_rate"] = (
                        total_stats["delivered"] / total_stats["sent"]
                    ) * 100
                    total_stats["bounce_rate"] = (
                        total_stats["bounced"] / total_stats["sent"]
                    ) * 100

                return total_stats
            else:
                raise ServiceError(
                    f"Failed to get domain stats: {response.status_code}",
                    error_code="STATS_FAILED",
                    details={"status_code": response.status_code},
                )

        except requests.exceptions.RequestException as e:
            raise ServiceError(
                f"Network error getting domain stats: {str(e)}",
                error_code="NETWORK_ERROR",
                details={"error": str(e)},
            )

    def add_template(self, template: EmailTemplate):
        """Add a custom email template"""
        self.templates[template.name] = template
        logger.info(f"Added email template: {template.name}")

    def get_templates(self) -> Dict[str, EmailTemplate]:
        """Get all available email templates"""
        return self.templates.copy()

    def health_check(self) -> Dict[str, Any]:
        """Check if Mailgun service is healthy"""
        try:
            # Test domain verification
            response = self.get(f"{self.base_url}/{self.domain}", auth=self.auth, timeout=5)

            if response.status_code == 200:
                domain_info = response.json().get("domain", {})
                return {
                    "status": "healthy",
                    "service": "mailgun",
                    "domain": self.domain,
                    "domain_state": domain_info.get("state", "unknown"),
                    "response_time": response.elapsed.total_seconds(),
                }
            else:
                return {
                    "status": "unhealthy",
                    "service": "mailgun",
                    "error": f"HTTP {response.status_code}",
                }

        except Exception as e:
            return {"status": "unhealthy", "service": "mailgun", "error": str(e)}
