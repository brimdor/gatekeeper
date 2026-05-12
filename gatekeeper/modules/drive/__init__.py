"""Google Drive module — file and folder operations."""

from __future__ import annotations

from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef


class DriveModule(GoogleModule):
    name = "drive"
    display_name = "Google Drive"
    description = "Browse, search, and read files in Google Drive"
    icon = "📁"

    required_scopes = ["https://www.googleapis.com/auth/drive.readonly"]

    def get_routes(self) -> list[RouteDef]:
        return [
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
                enabled_by_default=False,  # Write operation — off by default
            ),
        ]


Module = DriveModule