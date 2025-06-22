"""
Email Routes - API endpoints for email automation via Mailgun
"""

import logging

from flask import Blueprint, request # jsonify removed, error_response import will be removed

from src.config_flexible import get_config
from src.exceptions import ServiceError, SwarmException, ValidationError, EmailError # Added relevant exceptions
from src.services.mailgun_service import EmailMessage, MailgunService
from src.utils.response_helpers import create_success_response # error_response import removed

logger = logging.getLogger(__name__)

# Get flexible configuration
config = get_config()

# Initialize Mailgun service if API key is available
mailgun_service = None
if config.api.mailgun_api_key and config.api.mailgun_domain:
    try:
        mailgun_service = MailgunService(
            api_key=config.api.mailgun_api_key,
            domain=config.api.mailgun_domain,
            webhook_signing_key=config.api.mailgun_webhook_signing_key,
        )
        logger.info("Mailgun service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Mailgun service: {e}")
        mailgun_service = None
else:
    logger.warning("Mailgun service not configured - email features disabled")

email_bp = Blueprint("email", __name__)


@email_bp.route("/send", methods=["POST"])
def send_email():
    """Send an email"""
    try:
        data = request.get_json()

        if not data:
            raise ValidationError("Request body is required", error_code="MISSING_BODY")

        # Extract email data
        to = data.get("to", [])
        subject = data.get("subject", "")
        text_content = data.get("text_content", "")
        html_content = data.get("html_content")
        from_email = data.get("from_email")
        from_name = data.get("from_name")
        reply_to = data.get("reply_to")
        cc = data.get("cc", [])
        bcc = data.get("bcc", [])
        tags = data.get("tags", [])
        metadata = data.get("metadata", {})
        agent_id = data.get("agent_id", "unknown")

        # Validate required fields
        if not to:
            raise ValidationError("Recipients are required", error_code="MISSING_RECIPIENTS", details={"field": "to"})

        if not subject:
            raise ValidationError("Subject is required", error_code="MISSING_SUBJECT", details={"field": "subject"})

        if not text_content and not html_content:
            raise ValidationError("Email content is required", error_code="MISSING_CONTENT", details={"fields": ["text_content", "html_content"]})

        # Create email message
        message = EmailMessage(
            to=to if isinstance(to, list) else [to],
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
            cc=cc if isinstance(cc, list) else [cc] if cc else None,
            bcc=bcc if isinstance(bcc, list) else [bcc] if bcc else None,
            tags=tags if isinstance(tags, list) else [tags] if tags else None,
            metadata=metadata,
        )

        result = mailgun_service.send_email(message, agent_id)
        return create_success_response(result)
    except ValidationError:
        raise
    except ServiceError: # ServiceError is a SwarmException, re-raise
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        raise EmailError("Failed to send email due to an unexpected error", error_code="EMAIL_SEND_UNEXPECTED_ERROR", details={"original_error": str(e)})


@email_bp.route("/send-template", methods=["POST"])
def send_template_email():
    """Send email using a template"""
    try:
        data = request.get_json()

        if not data:
            raise ValidationError("Request body is required", error_code="MISSING_BODY")

        template_name = data.get("template_name")
        recipients = data.get("recipients", [])
        variables = data.get("variables", {})
        agent_id = data.get("agent_id", "unknown")

        if not template_name:
            raise ValidationError("Template name is required", error_code="MISSING_TEMPLATE_NAME", details={"field": "template_name"})

        if not recipients:
            raise ValidationError("Recipients are required", error_code="MISSING_RECIPIENTS", details={"field": "recipients"})

        result = mailgun_service.send_template_email(
            template_name,
            recipients if isinstance(recipients, list) else [recipients],
            variables,
            agent_id,
        )
        return create_success_response(result)
    except ValidationError:
        raise
    except ServiceError: # ServiceError is a SwarmException, re-raise
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending template email: {e}")
        raise EmailError("Failed to send template email due to an unexpected error", error_code="EMAIL_TEMPLATE_UNEXPECTED_ERROR", details={"original_error": str(e)})


@email_bp.route("/compose-ai", methods=["POST"])
def compose_ai_email():
    """Compose an email using AI"""
    try:
        data = request.get_json()

        if not data:
            raise ValidationError("Request body is required", error_code="MISSING_BODY")

        context = data.get("context", {})
        agent_id = data.get("agent_id", "email")
        send_immediately = data.get("send_immediately", False)

        if not context:
            raise ValidationError("Context is required for AI composition", error_code="MISSING_CONTEXT", details={"field": "context"})

        # Compose email using AI
        message = mailgun_service.compose_ai_email(context, agent_id)

        result = {
            "composed": True,
            "message": {
                "to": message.to,
                "subject": message.subject,
                "text_content": message.text_content,
                "html_content": message.html_content,
                "tags": message.tags,
                "metadata": message.metadata,
            },
        }

        # Send immediately if requested
        if send_immediately:
            send_result = mailgun_service.send_email(message, agent_id)
            result["sent"] = True
            result["send_result"] = send_result

        return create_success_response(result)
    except ValidationError:
        raise
    except ServiceError: # ServiceError is a SwarmException, re-raise
        raise
    except Exception as e:
        logger.error(f"Unexpected error composing AI email: {e}")
        raise EmailError("Failed to compose AI email due to an unexpected error", error_code="EMAIL_COMPOSE_AI_UNEXPECTED_ERROR", details={"original_error": str(e)})


@email_bp.route("/status/<message_id>", methods=["GET"])
def get_delivery_status(message_id):
    """Get delivery status for a message"""
    try:
        result = mailgun_service.get_delivery_status(message_id)
        return create_success_response({"status": result.__dict__})
    except ServiceError: # ServiceError is a SwarmException, re-raise
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting delivery status: {e}")
        raise EmailError("Failed to get delivery status due to an unexpected error", error_code="EMAIL_STATUS_UNEXPECTED_ERROR", details={"original_error": str(e)})


@email_bp.route("/webhooks/mailgun", methods=["POST"])
def mailgun_webhook():
    """Handle Mailgun webhooks"""
    try:
        # Verify webhook signature
        timestamp = request.form.get("timestamp")
        token = request.form.get("token")
        signature = request.form.get("signature")

        if not mailgun_service.verify_webhook(timestamp, token, signature):
            logger.warning("Invalid webhook signature")
            # Using SwarmException directly as this is a security/auth type of error
            raise SwarmException("Invalid webhook signature", error_code="INVALID_WEBHOOK_SIGNATURE", status_code=401)

        # Process webhook data
        webhook_data = request.get_json() or request.form.to_dict()
        result = mailgun_service.process_webhook(webhook_data)

        return create_success_response(result)
    except SwarmException: # Re-raise SwarmExceptions like the one from verify_webhook
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise EmailError("Webhook processing failed", error_code="EMAIL_WEBHOOK_PROCESSING_ERROR", details={"original_error": str(e)})


@email_bp.route("/templates", methods=["GET"])
def get_templates():
    """Get available email templates"""
    try:
        templates = mailgun_service.get_templates()

        # Convert templates to dict format
        template_list = []
        for name, template in templates.items():
            template_list.append(
                {
                    "name": template.name,
                    "subject": template.subject,
                    "description": template.description,
                    "variables": template.variables,
                }
            )

        return create_success_response({"templates": template_list})
    except ServiceError: # If mailgun_service.get_templates() raises it
        raise
    except Exception as e:
        logger.error(f"Error getting templates: {e}")
        raise EmailError("Failed to get templates", error_code="EMAIL_GET_TEMPLATES_ERROR", details={"original_error": str(e)})


@email_bp.route("/templates", methods=["POST"])
def add_template():
    """Add a custom email template"""
    try:
        data = request.get_json()

        if not data:
            raise ValidationError("Request body is required", error_code="MISSING_BODY")

        name = data.get("name")
        subject = data.get("subject")
        text_content = data.get("text_content")
        html_content = data.get("html_content")
        variables = data.get("variables", [])
        description = data.get("description")

        if not name:
            raise ValidationError("Template name is required", error_code="MISSING_TEMPLATE_NAME", details={"field": "name"})

        if not subject:
            raise ValidationError("Template subject is required", error_code="MISSING_TEMPLATE_SUBJECT", details={"field": "subject"})

        if not text_content:
            raise ValidationError("Template text content is required", error_code="MISSING_TEMPLATE_CONTENT", details={"field": "text_content"})

        # Create and add template
        from src.services.mailgun_service import EmailTemplate

        template = EmailTemplate(
            name=name,
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            variables=variables,
            description=description,
        )

        mailgun_service.add_template(template)

        return create_success_response({"message": f"Template '{name}' added successfully"})
    except ValidationError:
        raise
    except ServiceError: # If mailgun_service.add_template() raises it
        raise
    except Exception as e:
        logger.error(f"Error adding template: {e}")
        raise EmailError("Failed to add template", error_code="EMAIL_ADD_TEMPLATE_ERROR", details={"original_error": str(e)})


@email_bp.route("/stats", methods=["GET"])
def get_domain_stats():
    """Get domain email statistics"""
    try:
        result = mailgun_service.get_domain_stats()
        return create_success_response(result)
    except ServiceError: # ServiceError is a SwarmException, re-raise
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting domain stats: {e}")
        raise EmailError("Failed to get domain stats", error_code="EMAIL_STATS_UNEXPECTED_ERROR", details={"original_error": str(e)})


@email_bp.route("/health", methods=["GET"])
def health_check():
    """Health check for email service"""
    try:
        result = mailgun_service.health_check()
        return create_success_response(result)
    except ServiceError: # If health_check raises it
        raise
    except Exception as e:
        logger.error(f"Unexpected error in health check: {e}")
        raise EmailError("Email service health check failed", error_code="EMAIL_HEALTH_CHECK_ERROR", details={"original_error": str(e)})
