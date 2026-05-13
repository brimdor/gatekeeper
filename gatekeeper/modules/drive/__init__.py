"""Google Drive module — file and folder operations."""

from __future__ import annotations

from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef


class DriveModule(GoogleModule):
    name = "drive"
    display_name = "Google Drive"
    description = "Browse, search, and read files in Google Drive"
    icon = "📁"

    required_scopes = ["https://www.googleapis.com/auth/drive"]

    def get_routes(self) -> list[RouteDef]:
        return [
            # ── Read operations (on by default) ──
            RouteDef(
                route_id="drive.files.list",
                method="GET",
                google_path="/drive/v3/files",
                description="List and search for files in Drive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Drive query string (e.g., \"name contains 'report'\")",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of files to return (max 100)",
                            "default": 20,
                        },
                        "order_by": {
                            "type": "string",
                            "description": "Sort field (e.g., 'modifiedTime')",
                            "default": "modifiedTime",
                        },
                    },
                },
                default_policy={"max_results": 50},
            ),
            RouteDef(
                route_id="drive.files.get",
                method="GET",
                google_path="/drive/v3/files/{fileId}",
                description="Get file metadata by ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to retrieve",
                        },
                        "fields": {
                            "type": "string",
                            "description": "Fields to include in the response",
                            "default": "id,name,mimeType,size,modifiedTime,parents",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.files.export",
                method="GET",
                google_path="/drive/v3/files/{fileId}/export",
                description="Export a Google Workspace document to a given MIME type",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to export",
                        },
                        "mime_type": {
                            "type": "string",
                            "description": "Target MIME type (e.g., 'application/pdf')",
                            "default": "application/pdf",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.files.list_shared",
                method="GET",
                google_path="/drive/v3/files",
                description="List files shared with the user",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_size": {
                            "type": "integer",
                            "description": "Number of files to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={"max_results": 50, "query_filter": "sharedWithMe=true"},
            ),
            # ── Write operations (off by default) ──
            RouteDef(
                route_id="drive.files.copy",
                method="POST",
                google_path="/drive/v3/files/{fileId}/copy",
                description="Copy a file (requires drive scope)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file to copy",
                        },
                        "name": {
                            "type": "string",
                            "description": "Name for the copy",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.create",
                method="POST",
                google_path="/drive/v3/files",
                description="Upload or create a new file in Drive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the new file",
                        },
                        "mime_type": {
                            "type": "string",
                            "description": "MIME type of the file",
                        },
                        "parents": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Parent folder IDs to add the file to",
                        },
                    },
                    "required": ["name"],
                },
                default_policy={"max_file_size_mb": 25},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.update",
                method="PATCH",
                google_path="/drive/v3/files/{fileId}",
                description="Update file metadata or content",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to update",
                        },
                        "name": {
                            "type": "string",
                            "description": "New name for the file",
                        },
                        "description": {
                            "type": "string",
                            "description": "New description for the file",
                        },
                        "starred": {
                            "type": "boolean",
                            "description": "Whether the file is starred",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.delete",
                method="DELETE",
                google_path="/drive/v3/files/{fileId}",
                description="Permanently delete a file (cannot be undone)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to permanently delete",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.trash",
                method="POST",
                google_path="/drive/v3/files/{fileId}",
                description="Move a file to trash (recoverable)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to trash",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Permissions ──
            RouteDef(
                route_id="drive.permissions.list",
                method="GET",
                google_path="/drive/v3/files/{fileId}/permissions",
                description="See who a file is shared with",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to check permissions for",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.permissions.get",
                method="GET",
                google_path="/drive/v3/files/{fileId}/permissions/{permissionId}",
                description="Get details of a specific permission on a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file",
                        },
                        "permission_id": {
                            "type": "string",
                            "description": "The ID of the permission to retrieve",
                        },
                    },
                    "required": ["file_id", "permission_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.permissions.create",
                method="POST",
                google_path="/drive/v3/files/{fileId}/permissions",
                description="Share a file with someone — add a new permission",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to share",
                        },
                        "email_address": {
                            "type": "string",
                            "description": "Email address of the person to share with",
                        },
                        "role": {
                            "type": "string",
                            "description": "Role to grant: reader, writer, organizer, or owner",
                            "default": "reader",
                        },
                        "type": {
                            "type": "string",
                            "description": "Permission type: user, group, or anyone",
                            "default": "user",
                        },
                    },
                    "required": ["file_id", "email_address"],
                },
                default_policy={"max_recipients": 5},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.permissions.delete",
                method="DELETE",
                google_path="/drive/v3/files/{fileId}/permissions/{permissionId}",
                description="Remove someone's access to a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file",
                        },
                        "permission_id": {
                            "type": "string",
                            "description": "The ID of the permission to remove",
                        },
                    },
                    "required": ["file_id", "permission_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
        ]


Module = DriveModule