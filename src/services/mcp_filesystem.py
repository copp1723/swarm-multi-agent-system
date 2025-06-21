"""
MCP Filesystem Service - Model Context Protocol filesystem access for agents
"""

import os
import json
import logging
import mimetypes
import hashlib
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from pathlib import Path
import tempfile
import shutil
from src.services.base_service import BaseService, handle_service_errors
from src.exceptions import SwarmException, ServiceError

logger = logging.getLogger(__name__)

@dataclass
class FileInfo:
    """Represents file information"""
    path: str
    name: str
    size: int
    mime_type: str
    created_at: str
    modified_at: str
    is_directory: bool
    permissions: str
    checksum: Optional[str] = None

@dataclass
class FileOperation:
    """Represents a file operation for audit logging"""
    operation: str  # read, write, create, delete, move, copy
    path: str
    agent_id: str
    timestamp: str
    success: bool
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class MCPFilesystemService(BaseService):
    """Service for secure filesystem access via Model Context Protocol"""
    
    def __init__(self, base_path: str = "/tmp/swarm_workspace", max_file_size: int = 10 * 1024 * 1024):
        super().__init__("MCP_Filesystem")
        self.base_path = Path(base_path).resolve()
        self.max_file_size = max_file_size  # 10MB default
        self.allowed_extensions = {
            '.txt', '.md', '.json', '.yaml', '.yml', '.csv', '.log',
            '.py', '.js', '.html', '.css', '.xml', '.sql', '.sh',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'
        }
        self.operation_log = []
        
        # Create base workspace if it doesn't exist
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Set up secure permissions
        os.chmod(self.base_path, 0o755)
        
        logger.info(f"MCP Filesystem initialized with base path: {self.base_path}")
    
    def _validate_path(self, path: str) -> Path:
        """Validate and resolve path within workspace boundaries"""
        try:
            # Convert to Path object and resolve
            target_path = Path(path)
            
            # If relative path, make it relative to base_path
            if not target_path.is_absolute():
                target_path = self.base_path / target_path
            else:
                target_path = target_path.resolve()
            
            # Ensure path is within workspace
            try:
                target_path.relative_to(self.base_path)
            except ValueError:
                raise ServiceError(
                    f"Path outside workspace: {path}",
                    error_code="PATH_OUTSIDE_WORKSPACE",
                    details={"path": str(path), "workspace": str(self.base_path)}
                )
            
            return target_path
            
        except Exception as e:
            raise ServiceError(
                f"Invalid path: {path}",
                error_code="INVALID_PATH",
                details={"path": str(path), "error": str(e)}
            )
    
    def _validate_file_extension(self, path: Path) -> bool:
        """Check if file extension is allowed"""
        return path.suffix.lower() in self.allowed_extensions
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception:
            return ""
    
    def _log_operation(self, operation: str, path: str, agent_id: str, 
                      success: bool, error_message: str = None, metadata: Dict[str, Any] = None):
        """Log file operation for audit trail"""
        op = FileOperation(
            operation=operation,
            path=path,
            agent_id=agent_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=success,
            error_message=error_message,
            metadata=metadata or {}
        )
        self.operation_log.append(op)
        
        # Keep only last 1000 operations
        if len(self.operation_log) > 1000:
            self.operation_log = self.operation_log[-1000:]
        
        # Log to file as well
        log_level = logging.INFO if success else logging.ERROR
        logger.log(log_level, f"MCP Operation: {operation} {path} by {agent_id} - {'SUCCESS' if success else 'FAILED'}")
    
    @handle_service_errors
    def read_file(self, path: str, agent_id: str, encoding: str = 'utf-8') -> Dict[str, Any]:
        """Read file content"""
        target_path = self._validate_path(path)
        
        try:
            if not target_path.exists():
                raise ServiceError(
                    f"File not found: {path}",
                    error_code="FILE_NOT_FOUND",
                    details={"path": str(target_path)}
                )
            
            if target_path.is_dir():
                raise ServiceError(
                    f"Path is a directory: {path}",
                    error_code="IS_DIRECTORY",
                    details={"path": str(target_path)}
                )
            
            # Check file size
            file_size = target_path.stat().st_size
            if file_size > self.max_file_size:
                raise ServiceError(
                    f"File too large: {file_size} bytes (max: {self.max_file_size})",
                    error_code="FILE_TOO_LARGE",
                    details={"size": file_size, "max_size": self.max_file_size}
                )
            
            # Read file content
            try:
                with open(target_path, 'r', encoding=encoding) as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Try binary read for non-text files
                with open(target_path, 'rb') as f:
                    content = f.read()
                    # Convert to base64 for safe transport
                    import base64
                    content = base64.b64encode(content).decode('ascii')
                    encoding = 'base64'
            
            file_info = self._get_file_info(target_path)
            
            self._log_operation("read", str(target_path), agent_id, True, 
                              metadata={"size": file_size, "encoding": encoding})
            
            return {
                "content": content,
                "encoding": encoding,
                "file_info": asdict(file_info)
            }
            
        except ServiceError:
            raise
        except Exception as e:
            self._log_operation("read", str(target_path), agent_id, False, str(e))
            raise ServiceError(
                f"Failed to read file: {str(e)}",
                error_code="READ_FAILED",
                details={"path": str(target_path), "error": str(e)}
            )
    
    @handle_service_errors
    def write_file(self, path: str, content: str, agent_id: str, 
                   encoding: str = 'utf-8', overwrite: bool = False) -> Dict[str, Any]:
        """Write content to file"""
        target_path = self._validate_path(path)
        
        try:
            # Check if file exists and overwrite is not allowed
            if target_path.exists() and not overwrite:
                raise ServiceError(
                    f"File exists and overwrite not allowed: {path}",
                    error_code="FILE_EXISTS",
                    details={"path": str(target_path)}
                )
            
            # Validate file extension
            if not self._validate_file_extension(target_path):
                raise ServiceError(
                    f"File extension not allowed: {target_path.suffix}",
                    error_code="EXTENSION_NOT_ALLOWED",
                    details={"extension": target_path.suffix, "allowed": list(self.allowed_extensions)}
                )
            
            # Create parent directories if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Handle different encodings
            if encoding == 'base64':
                import base64
                content_bytes = base64.b64decode(content)
                with open(target_path, 'wb') as f:
                    f.write(content_bytes)
            else:
                with open(target_path, 'w', encoding=encoding) as f:
                    f.write(content)
            
            # Set secure permissions
            os.chmod(target_path, 0o644)
            
            file_info = self._get_file_info(target_path)
            
            self._log_operation("write", str(target_path), agent_id, True,
                              metadata={"size": len(content), "encoding": encoding, "overwrite": overwrite})
            
            return {
                "success": True,
                "file_info": asdict(file_info)
            }
            
        except ServiceError:
            raise
        except Exception as e:
            self._log_operation("write", str(target_path), agent_id, False, str(e))
            raise ServiceError(
                f"Failed to write file: {str(e)}",
                error_code="WRITE_FAILED",
                details={"path": str(target_path), "error": str(e)}
            )
    
    @handle_service_errors
    def create_directory(self, path: str, agent_id: str) -> Dict[str, Any]:
        """Create directory"""
        target_path = self._validate_path(path)
        
        try:
            if target_path.exists():
                if target_path.is_dir():
                    self._log_operation("create_dir", str(target_path), agent_id, True,
                                      metadata={"already_exists": True})
                    return {"success": True, "message": "Directory already exists"}
                else:
                    raise ServiceError(
                        f"Path exists but is not a directory: {path}",
                        error_code="NOT_A_DIRECTORY",
                        details={"path": str(target_path)}
                    )
            
            target_path.mkdir(parents=True, exist_ok=True)
            os.chmod(target_path, 0o755)
            
            self._log_operation("create_dir", str(target_path), agent_id, True)
            
            return {"success": True, "path": str(target_path)}
            
        except ServiceError:
            raise
        except Exception as e:
            self._log_operation("create_dir", str(target_path), agent_id, False, str(e))
            raise ServiceError(
                f"Failed to create directory: {str(e)}",
                error_code="CREATE_DIR_FAILED",
                details={"path": str(target_path), "error": str(e)}
            )
    
    @handle_service_errors
    def delete_file(self, path: str, agent_id: str) -> Dict[str, Any]:
        """Delete file or directory"""
        target_path = self._validate_path(path)
        
        try:
            if not target_path.exists():
                raise ServiceError(
                    f"Path not found: {path}",
                    error_code="PATH_NOT_FOUND",
                    details={"path": str(target_path)}
                )
            
            if target_path.is_dir():
                shutil.rmtree(target_path)
                operation = "delete_dir"
            else:
                target_path.unlink()
                operation = "delete_file"
            
            self._log_operation(operation, str(target_path), agent_id, True)
            
            return {"success": True, "path": str(target_path)}
            
        except ServiceError:
            raise
        except Exception as e:
            self._log_operation("delete", str(target_path), agent_id, False, str(e))
            raise ServiceError(
                f"Failed to delete: {str(e)}",
                error_code="DELETE_FAILED",
                details={"path": str(target_path), "error": str(e)}
            )
    
    @handle_service_errors
    def list_directory(self, path: str, agent_id: str, include_hidden: bool = False) -> Dict[str, Any]:
        """List directory contents"""
        target_path = self._validate_path(path)
        
        try:
            if not target_path.exists():
                raise ServiceError(
                    f"Directory not found: {path}",
                    error_code="DIRECTORY_NOT_FOUND",
                    details={"path": str(target_path)}
                )
            
            if not target_path.is_dir():
                raise ServiceError(
                    f"Path is not a directory: {path}",
                    error_code="NOT_A_DIRECTORY",
                    details={"path": str(target_path)}
                )
            
            items = []
            for item in target_path.iterdir():
                # Skip hidden files unless requested
                if not include_hidden and item.name.startswith('.'):
                    continue
                
                file_info = self._get_file_info(item)
                items.append(asdict(file_info))
            
            # Sort by name
            items.sort(key=lambda x: x['name'].lower())
            
            self._log_operation("list_dir", str(target_path), agent_id, True,
                              metadata={"item_count": len(items), "include_hidden": include_hidden})
            
            return {
                "path": str(target_path),
                "items": items,
                "total_count": len(items)
            }
            
        except ServiceError:
            raise
        except Exception as e:
            self._log_operation("list_dir", str(target_path), agent_id, False, str(e))
            raise ServiceError(
                f"Failed to list directory: {str(e)}",
                error_code="LIST_DIR_FAILED",
                details={"path": str(target_path), "error": str(e)}
            )
    
    @handle_service_errors
    def move_file(self, source_path: str, dest_path: str, agent_id: str) -> Dict[str, Any]:
        """Move/rename file or directory"""
        source = self._validate_path(source_path)
        dest = self._validate_path(dest_path)
        
        try:
            if not source.exists():
                raise ServiceError(
                    f"Source not found: {source_path}",
                    error_code="SOURCE_NOT_FOUND",
                    details={"source": str(source)}
                )
            
            if dest.exists():
                raise ServiceError(
                    f"Destination already exists: {dest_path}",
                    error_code="DESTINATION_EXISTS",
                    details={"destination": str(dest)}
                )
            
            # Create parent directory if needed
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.move(str(source), str(dest))
            
            self._log_operation("move", f"{source} -> {dest}", agent_id, True)
            
            return {
                "success": True,
                "source": str(source),
                "destination": str(dest)
            }
            
        except ServiceError:
            raise
        except Exception as e:
            self._log_operation("move", f"{source} -> {dest}", agent_id, False, str(e))
            raise ServiceError(
                f"Failed to move file: {str(e)}",
                error_code="MOVE_FAILED",
                details={"source": str(source), "destination": str(dest), "error": str(e)}
            )
    
    @handle_service_errors
    def copy_file(self, source_path: str, dest_path: str, agent_id: str) -> Dict[str, Any]:
        """Copy file or directory"""
        source = self._validate_path(source_path)
        dest = self._validate_path(dest_path)
        
        try:
            if not source.exists():
                raise ServiceError(
                    f"Source not found: {source_path}",
                    error_code="SOURCE_NOT_FOUND",
                    details={"source": str(source)}
                )
            
            if dest.exists():
                raise ServiceError(
                    f"Destination already exists: {dest_path}",
                    error_code="DESTINATION_EXISTS",
                    details={"destination": str(dest)}
                )
            
            # Create parent directory if needed
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            if source.is_dir():
                shutil.copytree(str(source), str(dest))
            else:
                shutil.copy2(str(source), str(dest))
            
            self._log_operation("copy", f"{source} -> {dest}", agent_id, True)
            
            return {
                "success": True,
                "source": str(source),
                "destination": str(dest)
            }
            
        except ServiceError:
            raise
        except Exception as e:
            self._log_operation("copy", f"{source} -> {dest}", agent_id, False, str(e))
            raise ServiceError(
                f"Failed to copy file: {str(e)}",
                error_code="COPY_FAILED",
                details={"source": str(source), "destination": str(dest), "error": str(e)}
            )
    
    def _get_file_info(self, path: Path) -> FileInfo:
        """Get file information"""
        stat = path.stat()
        
        return FileInfo(
            path=str(path),
            name=path.name,
            size=stat.st_size,
            mime_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream',
            created_at=datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat(),
            modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            is_directory=path.is_dir(),
            permissions=oct(stat.st_mode)[-3:],
            checksum=self._calculate_checksum(path) if path.is_file() else None
        )
    
    @handle_service_errors
    def get_file_info(self, path: str, agent_id: str) -> Dict[str, Any]:
        """Get detailed file information"""
        target_path = self._validate_path(path)
        
        try:
            if not target_path.exists():
                raise ServiceError(
                    f"Path not found: {path}",
                    error_code="PATH_NOT_FOUND",
                    details={"path": str(target_path)}
                )
            
            file_info = self._get_file_info(target_path)
            
            self._log_operation("info", str(target_path), agent_id, True)
            
            return asdict(file_info)
            
        except ServiceError:
            raise
        except Exception as e:
            self._log_operation("info", str(target_path), agent_id, False, str(e))
            raise ServiceError(
                f"Failed to get file info: {str(e)}",
                error_code="INFO_FAILED",
                details={"path": str(target_path), "error": str(e)}
            )
    
    def get_operation_log(self, agent_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get operation log for audit purposes"""
        operations = self.operation_log
        
        if agent_id:
            operations = [op for op in operations if op.agent_id == agent_id]
        
        # Return most recent operations
        operations = operations[-limit:]
        
        return [asdict(op) for op in operations]
    
    def get_workspace_stats(self) -> Dict[str, Any]:
        """Get workspace statistics"""
        try:
            total_size = 0
            file_count = 0
            dir_count = 0
            
            for root, dirs, files in os.walk(self.base_path):
                dir_count += len(dirs)
                for file in files:
                    file_path = Path(root) / file
                    try:
                        total_size += file_path.stat().st_size
                        file_count += 1
                    except (OSError, IOError):
                        pass  # Skip files we can't access
            
            return {
                "workspace_path": str(self.base_path),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "file_count": file_count,
                "directory_count": dir_count,
                "max_file_size_mb": round(self.max_file_size / (1024 * 1024), 2),
                "allowed_extensions": list(self.allowed_extensions)
            }
            
        except Exception as e:
            return {
                "error": f"Failed to get workspace stats: {str(e)}",
                "workspace_path": str(self.base_path)
            }
    
    def health_check(self) -> Dict[str, Any]:
        """Check if MCP filesystem service is healthy"""
        try:
            # Test basic operations
            test_file = self.base_path / ".health_check"
            
            # Test write
            with open(test_file, 'w') as f:
                f.write("health_check")
            
            # Test read
            with open(test_file, 'r') as f:
                content = f.read()
            
            # Test delete
            test_file.unlink()
            
            if content == "health_check":
                return {
                    "status": "healthy",
                    "service": "mcp_filesystem",
                    "workspace": str(self.base_path),
                    "operations": ["read", "write", "delete"]
                }
            else:
                return {
                    "status": "unhealthy",
                    "service": "mcp_filesystem",
                    "error": "Content mismatch in health check"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "mcp_filesystem",
                "error": str(e)
            }

