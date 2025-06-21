"""
Email Routes - API endpoints for email automation via Mailgun
"""

from flask import Blueprint, request, jsonify
import logging
from src.services.mailgun_service import MailgunService, EmailMessage
from src.utils.response_helpers import success_response, error_response
from src.exceptions import SwarmException, ServiceError
from src.config import config

logger = logging.getLogger(__name__)

# Initialize Mailgun service
mailgun_service = MailgunService(
    api_key=config.mailgun_api_key,
    domain=config.mailgun_domain,
    webhook_signing_key=config.mailgun_webhook_signing_key
)

email_bp = Blueprint('email', __name__)

@email_bp.route('/send', methods=['POST'])
def send_email():
    """Send an email"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        # Extract email data
        to = data.get('to', [])
        subject = data.get('subject', '')
        text_content = data.get('text_content', '')
        html_content = data.get('html_content')
        from_email = data.get('from_email')
        from_name = data.get('from_name')
        reply_to = data.get('reply_to')
        cc = data.get('cc', [])
        bcc = data.get('bcc', [])
        tags = data.get('tags', [])
        metadata = data.get('metadata', {})
        agent_id = data.get('agent_id', 'unknown')
        
        # Validate required fields
        if not to:
            return error_response("Recipients are required", "MISSING_RECIPIENTS"), 400
        
        if not subject:
            return error_response("Subject is required", "MISSING_SUBJECT"), 400
        
        if not text_content and not html_content:
            return error_response("Email content is required", "MISSING_CONTENT"), 400
        
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
            metadata=metadata
        )
        
        result = mailgun_service.send_email(message, agent_id)
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error sending email: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@email_bp.route('/send-template', methods=['POST'])
def send_template_email():
    """Send email using a template"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        template_name = data.get('template_name')
        recipients = data.get('recipients', [])
        variables = data.get('variables', {})
        agent_id = data.get('agent_id', 'unknown')
        
        if not template_name:
            return error_response("Template name is required", "MISSING_TEMPLATE_NAME"), 400
        
        if not recipients:
            return error_response("Recipients are required", "MISSING_RECIPIENTS"), 400
        
        result = mailgun_service.send_template_email(
            template_name, 
            recipients if isinstance(recipients, list) else [recipients],
            variables,
            agent_id
        )
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error sending template email: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error sending template email: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@email_bp.route('/compose-ai', methods=['POST'])
def compose_ai_email():
    """Compose an email using AI"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        context = data.get('context', {})
        agent_id = data.get('agent_id', 'email')
        send_immediately = data.get('send_immediately', False)
        
        if not context:
            return error_response("Context is required for AI composition", "MISSING_CONTEXT"), 400
        
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
                "metadata": message.metadata
            }
        }
        
        # Send immediately if requested
        if send_immediately:
            send_result = mailgun_service.send_email(message, agent_id)
            result["sent"] = True
            result["send_result"] = send_result
        
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error composing AI email: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error composing AI email: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@email_bp.route('/status/<message_id>', methods=['GET'])
def get_delivery_status(message_id):
    """Get delivery status for a message"""
    try:
        result = mailgun_service.get_delivery_status(message_id)
        return success_response({"status": result.__dict__})
        
    except ServiceError as e:
        logger.error(f"Service error getting delivery status: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error getting delivery status: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@email_bp.route('/webhooks/mailgun', methods=['POST'])
def mailgun_webhook():
    """Handle Mailgun webhooks"""
    try:
        # Verify webhook signature
        timestamp = request.form.get('timestamp')
        token = request.form.get('token')
        signature = request.form.get('signature')
        
        if not mailgun_service.verify_webhook(timestamp, token, signature):
            logger.warning("Invalid webhook signature")
            return error_response("Invalid signature", "INVALID_SIGNATURE"), 401
        
        # Process webhook data
        webhook_data = request.get_json() or request.form.to_dict()
        result = mailgun_service.process_webhook(webhook_data)
        
        return success_response(result)
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return error_response("Webhook processing failed", "WEBHOOK_ERROR"), 500

@email_bp.route('/templates', methods=['GET'])
def get_templates():
    """Get available email templates"""
    try:
        templates = mailgun_service.get_templates()
        
        # Convert templates to dict format
        template_list = []
        for name, template in templates.items():
            template_list.append({
                "name": template.name,
                "subject": template.subject,
                "description": template.description,
                "variables": template.variables
            })
        
        return success_response({"templates": template_list})
        
    except Exception as e:
        logger.error(f"Error getting templates: {e}")
        return error_response("Failed to get templates", "TEMPLATES_ERROR"), 500

@email_bp.route('/templates', methods=['POST'])
def add_template():
    """Add a custom email template"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        name = data.get('name')
        subject = data.get('subject')
        text_content = data.get('text_content')
        html_content = data.get('html_content')
        variables = data.get('variables', [])
        description = data.get('description')
        
        if not name:
            return error_response("Template name is required", "MISSING_NAME"), 400
        
        if not subject:
            return error_response("Template subject is required", "MISSING_SUBJECT"), 400
        
        if not text_content:
            return error_response("Template text content is required", "MISSING_CONTENT"), 400
        
        # Create and add template
        from src.services.mailgun_service import EmailTemplate
        template = EmailTemplate(
            name=name,
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            variables=variables,
            description=description
        )
        
        mailgun_service.add_template(template)
        
        return success_response({"message": f"Template '{name}' added successfully"})
        
    except Exception as e:
        logger.error(f"Error adding template: {e}")
        return error_response("Failed to add template", "ADD_TEMPLATE_ERROR"), 500

@email_bp.route('/stats', methods=['GET'])
def get_domain_stats():
    """Get domain email statistics"""
    try:
        result = mailgun_service.get_domain_stats()
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error getting domain stats: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error getting domain stats: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@email_bp.route('/health', methods=['GET'])
def health_check():
    """Health check for email service"""
    try:
        result = mailgun_service.health_check()
        return success_response(result)
        
    except Exception as e:
        logger.error(f"Unexpected error in health check: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

