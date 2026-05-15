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
                        "q": {
                            "type": "string",
                            "description": (
                                "Drive query string "
                                "(e.g., \"name contains 'report'\"). "
                                "See: https://developers.google.com/"
                                "drive/api/v3/search-files"
                            ),
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
                        "fields": {
                            "type": "string",
                            "description": (
                                "Fields to include in the response "
                                "(e.g., 'files(id,name,mimeType)')"
                            ),
                            "default": (
                                "files(id,name,mimeType,modifiedTime,"
                                "size,owners,shared,parents),nextPageToken"
                            ),
                        },
                    },
                },
                # fields must be a query param — Google Drive API ignores it in the body
                query_params=["fields"],
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
                            "default": "id,name,mimeType,modifiedTime,size,owners,shared,parents",
                        },
                    },
                    "required": ["file_id"],
                },
                # fields must be a query param — Google Drive API ignores it in the body
                query_params=["fields"],
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
                        "shortcut_target_id": {
                            "type": "string",
                            "description": (
                                "File ID the shortcut points to "
                                "(only used when mime_type is shortcut)"
                            ),
                        },
                        "shortcut_target_mime_type": {
                            "type": "string",
                            "description": (
                                "MIME type of the target file "
                                "(only used when mime_type is shortcut)"
                            ),
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
                        "add_parents": {
                            "type": "string",
                            "description": (
                                "Comma-separated parent folder IDs to add (for moving files)"
                            ),
                        },
                        "remove_parents": {
                            "type": "string",
                            "description": (
                                "Comma-separated parent folder IDs to remove (for moving files)"
                            ),
                        },
                    },
                    "required": ["file_id"],
                },
                # addParents/removeParents MUST be query params, not body —
                # Google Drive API silently ignores them in the PATCH body.
                query_params=["addParents", "removeParents"],
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
            # ── About ──
            RouteDef(
                route_id="drive.about.get",
                method="GET",
                google_path="/drive/v3/about",
                description="Get user Drive storage quota and usage info",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            # ── Changes ──
            RouteDef(
                route_id="drive.changes.list",
                method="GET",
                google_path="/drive/v3/changes",
                description="List changes to files (incremental sync)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_token": {
                            "type": "string",
                            "description": ("Token for continuing a previous list request"),
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of changes to return",
                            "default": 100,
                        },
                    },
                },
                default_policy={"max_results": 100},
            ),
            RouteDef(
                route_id="drive.changes.get_start_page_token",
                method="GET",
                google_path="/drive/v3/changes/startPageToken",
                description="Get start page token for change tracking",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            # ── Comments ──
            RouteDef(
                route_id="drive.comments.list",
                method="GET",
                google_path="/drive/v3/files/{fileId}/comments",
                description="List comments on a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of comments to return",
                            "default": 20,
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.comments.get",
                method="GET",
                google_path=("/drive/v3/files/{fileId}/comments/{commentId}"),
                description="Get a comment by ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "comment_id": {
                            "type": "string",
                            "description": "ID of the comment",
                        },
                    },
                    "required": ["file_id", "comment_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.comments.create",
                method="POST",
                google_path="/drive/v3/files/{fileId}/comments",
                description="Create a comment on a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "content": {
                            "type": "string",
                            "description": "Comment text",
                        },
                    },
                    "required": ["file_id", "content"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Shared Drives ──
            RouteDef(
                route_id="drive.drives.list",
                method="GET",
                google_path="/drive/v3/drives",
                description="List shared drives",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_size": {
                            "type": "integer",
                            "description": "Number of drives to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={"max_results": 50},
            ),
            RouteDef(
                route_id="drive.drives.get",
                method="GET",
                google_path="/drive/v3/drives/{driveId}",
                description="Get shared drive metadata",
                input_schema={
                    "type": "object",
                    "properties": {
                        "drive_id": {
                            "type": "string",
                            "description": "ID of the shared drive",
                        },
                    },
                    "required": ["drive_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.drives.create",
                method="POST",
                google_path="/drive/v3/drives",
                description="Create a shared drive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the new shared drive",
                        },
                    },
                    "required": ["name"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Files (additional) ──
            RouteDef(
                route_id="drive.files.empty_trash",
                method="DELETE",
                google_path="/drive/v3/files/trash",
                description="Permanently delete all trashed files",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.generate_ids",
                method="GET",
                google_path="/drive/v3/files/generateIds",
                description="Generate file IDs for future uploads",
                input_schema={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of IDs to generate",
                            "default": 10,
                        },
                    },
                },
                default_policy={},
            ),
            # ── Permissions (continued) ──
            RouteDef(
                route_id="drive.permissions.update",
                method="PATCH",
                google_path=("/drive/v3/files/{fileId}/permissions/{permissionId}"),
                description="Update a permission on a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "permission_id": {
                            "type": "string",
                            "description": "ID of the permission to update",
                        },
                        "role": {
                            "type": "string",
                            "description": ("New role: reader, writer, organizer, or owner"),
                        },
                    },
                    "required": ["file_id", "permission_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Revisions ──
            RouteDef(
                route_id="drive.revisions.list",
                method="GET",
                google_path="/drive/v3/files/{fileId}/revisions",
                description="List file revisions",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of revisions to return",
                            "default": 20,
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.revisions.get",
                method="GET",
                google_path=("/drive/v3/files/{fileId}/revisions/{revisionId}"),
                description="Get a specific file revision",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "revision_id": {
                            "type": "string",
                            "description": "ID of the revision",
                        },
                    },
                    "required": ["file_id", "revision_id"],
                },
                default_policy={},
            ),
        ]


Module = DriveModule
