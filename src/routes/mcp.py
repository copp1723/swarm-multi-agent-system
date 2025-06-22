"""
MCP Status API endpoint for checking filesystem service health
"""

from flask import Blueprint, jsonify, current_app
from src.exceptions import SwarmException
import logging

logger = logging.getLogger(__name__)

mcp_bp = Blueprint('mcp', __name__, url_prefix='/api/mcp')


@mcp_bp.route('/status', methods=['GET'])
def get_mcp_status():
    """Get MCP filesystem service status"""
    try:
        # Get MCP filesystem service from app context
        mcp_service = getattr(current_app, 'mcp_filesystem_service', None)
        
        if not mcp_service:
            return jsonify({
                'status': 'disconnected',
                'error': 'MCP filesystem service not initialized',
                'service_name': 'mcp_filesystem'
            }), 200
        
        # Get health check and stats
        health = mcp_service.health_check()
        stats = mcp_service.get_workspace_stats()
        
        return jsonify({
            'status': health.get('status', 'unknown'),
            'health': health,
            'stats': stats,
            'service_name': 'mcp_filesystem'
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get MCP status: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'service_name': 'mcp_filesystem'
        }), 200  # Return 200 to avoid client errors


@mcp_bp.route('/workspace/info', methods=['GET'])
def get_workspace_info():
    """Get detailed workspace information"""
    try:
        mcp_service = getattr(current_app, 'mcp_filesystem_service', None)
        
        if not mcp_service:
            return jsonify({
                'success': False,
                'error': 'MCP filesystem service not available'
            }), 404
        
        stats = mcp_service.get_workspace_stats()
        
        return jsonify({
            'success': True,
            'data': stats
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get workspace info: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@mcp_bp.route('/operations/log', methods=['GET'])
def get_operation_log():
    """Get recent MCP filesystem operations"""
    try:
        mcp_service = getattr(current_app, 'mcp_filesystem_service', None)
        
        if not mcp_service:
            return jsonify({
                'success': False,
                'error': 'MCP filesystem service not available'
            }), 404
        
        operations = mcp_service.get_operation_log(limit=50)
        
        return jsonify({
            'success': True,
            'data': {
                'operations': operations,
                'total_count': len(operations)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get operation log: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

