"""
MCP Filesystem Routes - API endpoints for file operations
"""

from flask import Blueprint, request, jsonify
import logging
from src.services.mcp_filesystem import MCPFilesystemService
from src.utils.response_helpers import success_response, error_response
from src.exceptions import SwarmException, ServiceError

logger = logging.getLogger(__name__)

# Initialize MCP filesystem service
mcp_filesystem = MCPFilesystemService()

mcp_bp = Blueprint('mcp', __name__)

@mcp_bp.route('/files/read', methods=['POST'])
def read_file():
    """Read file content"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        path = data.get('path')
        agent_id = data.get('agent_id', 'unknown')
        encoding = data.get('encoding', 'utf-8')
        
        if not path:
            return error_response("File path is required", "MISSING_PATH"), 400
        
        result = mcp_filesystem.read_file(path, agent_id, encoding)
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error reading file: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error reading file: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@mcp_bp.route('/files/write', methods=['POST'])
def write_file():
    """Write content to file"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        path = data.get('path')
        content = data.get('content')
        agent_id = data.get('agent_id', 'unknown')
        encoding = data.get('encoding', 'utf-8')
        overwrite = data.get('overwrite', False)
        
        if not path:
            return error_response("File path is required", "MISSING_PATH"), 400
        
        if content is None:
            return error_response("File content is required", "MISSING_CONTENT"), 400
        
        result = mcp_filesystem.write_file(path, content, agent_id, encoding, overwrite)
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error writing file: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error writing file: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@mcp_bp.route('/files/create-directory', methods=['POST'])
def create_directory():
    """Create directory"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        path = data.get('path')
        agent_id = data.get('agent_id', 'unknown')
        
        if not path:
            return error_response("Directory path is required", "MISSING_PATH"), 400
        
        result = mcp_filesystem.create_directory(path, agent_id)
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error creating directory: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error creating directory: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@mcp_bp.route('/files/delete', methods=['POST'])
def delete_file():
    """Delete file or directory"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        path = data.get('path')
        agent_id = data.get('agent_id', 'unknown')
        
        if not path:
            return error_response("File path is required", "MISSING_PATH"), 400
        
        result = mcp_filesystem.delete_file(path, agent_id)
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error deleting file: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error deleting file: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@mcp_bp.route('/files/list', methods=['POST'])
def list_directory():
    """List directory contents"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        path = data.get('path', '.')
        agent_id = data.get('agent_id', 'unknown')
        include_hidden = data.get('include_hidden', False)
        
        result = mcp_filesystem.list_directory(path, agent_id, include_hidden)
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error listing directory: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error listing directory: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@mcp_bp.route('/files/move', methods=['POST'])
def move_file():
    """Move/rename file or directory"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        source_path = data.get('source_path')
        dest_path = data.get('dest_path')
        agent_id = data.get('agent_id', 'unknown')
        
        if not source_path:
            return error_response("Source path is required", "MISSING_SOURCE_PATH"), 400
        
        if not dest_path:
            return error_response("Destination path is required", "MISSING_DEST_PATH"), 400
        
        result = mcp_filesystem.move_file(source_path, dest_path, agent_id)
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error moving file: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error moving file: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@mcp_bp.route('/files/copy', methods=['POST'])
def copy_file():
    """Copy file or directory"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        source_path = data.get('source_path')
        dest_path = data.get('dest_path')
        agent_id = data.get('agent_id', 'unknown')
        
        if not source_path:
            return error_response("Source path is required", "MISSING_SOURCE_PATH"), 400
        
        if not dest_path:
            return error_response("Destination path is required", "MISSING_DEST_PATH"), 400
        
        result = mcp_filesystem.copy_file(source_path, dest_path, agent_id)
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error copying file: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error copying file: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@mcp_bp.route('/files/info', methods=['POST'])
def get_file_info():
    """Get file information"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body is required", "MISSING_BODY"), 400
        
        path = data.get('path')
        agent_id = data.get('agent_id', 'unknown')
        
        if not path:
            return error_response("File path is required", "MISSING_PATH"), 400
        
        result = mcp_filesystem.get_file_info(path, agent_id)
        return success_response(result)
        
    except ServiceError as e:
        logger.error(f"Service error getting file info: {e}")
        return error_response(e.message, e.error_code, e.details), 400
    except Exception as e:
        logger.error(f"Unexpected error getting file info: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@mcp_bp.route('/files/operations', methods=['GET'])
def get_operation_log():
    """Get file operation log"""
    try:
        agent_id = request.args.get('agent_id')
        limit = int(request.args.get('limit', 100))
        
        result = mcp_filesystem.get_operation_log(agent_id, limit)
        return success_response({"operations": result})
        
    except ValueError:
        return error_response("Invalid limit parameter", "INVALID_LIMIT"), 400
    except Exception as e:
        logger.error(f"Unexpected error getting operation log: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@mcp_bp.route('/workspace/stats', methods=['GET'])
def get_workspace_stats():
    """Get workspace statistics"""
    try:
        result = mcp_filesystem.get_workspace_stats()
        return success_response(result)
        
    except Exception as e:
        logger.error(f"Unexpected error getting workspace stats: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

@mcp_bp.route('/health', methods=['GET'])
def health_check():
    """Health check for MCP filesystem service"""
    try:
        result = mcp_filesystem.health_check()
        return success_response(result)
        
    except Exception as e:
        logger.error(f"Unexpected error in health check: {e}")
        return error_response("Internal server error", "INTERNAL_ERROR"), 500

