"""Google Gmail module — read and send email with policy controls."""

from __future__ import annotations

from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef


class GmailModule(GoogleModule):
    name = "gmail"
    display_name = "Google Gmail"
    description = "Read, search, and send email via Gmail"
    icon = "📧"

    required_scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
    ]

    def get_routes(self) -> list[RouteDef]:
        return [
            RouteDef(
                route_id="gmail.messages.list",
                method="GET",
                google_path="/gmail/v1/users/me/messages",
                description="List messages in the user's mailbox",
                input_schema={
                    "type": "object",
                    "properties": {
                        "label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Label IDs to filter by (e.g., ['INBOX', 'UNREAD'])",
                        },
                        "query": {
                            "type": "string",
                            "description": "Gmail search query (e.g., 'from:alice subject:report')",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of messages to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={
                    "max_results": 50,
                    "allowed_labels": ["INBOX", "SENT", "DRAFT", "UNREAD", "IMPORTANT"],
                    "exclude_labels": ["SPAM", "TRASH"],
                },
            ),
            RouteDef(
                route_id="gmail.messages.get",
                method="GET",
                google_path="/gmail/v1/users/me/messages/{messageId}",
                description="Get a specific message by ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "The ID of the message to retrieve",
                        },
                        "format": {
                            "type": "string",
                            "description": "Format: full, minimal, raw, metadata",
                            "default": "full",
                        },
                    },
                    "required": ["message_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.messages.send",
                method="POST",
                google_path="/gmail/v1/users/me/messages/send",
                description="Send an email message",
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Recipient email addresses",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject line",
                        },
                        "body": {
                            "type": "string",
                            "description": "Email body text",
                        },
                    },
                    "required": ["to", "subject", "body"],
                },
                default_policy={
                    "max_recipients": 5,
                    "max_attachment_size_mb": 10,
                    "require_body": True,
                },
                enabled_by_default=False,  # Write operation — off by default
            ),
            RouteDef(
                route_id="gmail.drafts.list",
                method="GET",
                google_path="/gmail/v1/users/me/drafts",
                description="List draft messages",
                input_schema={
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of drafts to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={"max_results": 50},
            ),
            RouteDef(
                route_id="gmail.drafts.create",
                method="POST",
                google_path="/gmail/v1/users/me/drafts",
                description="Create a new draft message",
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Recipient email addresses",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject line",
                        },
                        "body": {
                            "type": "string",
                            "description": "Email body text",
                        },
                    },
                    "required": ["to", "subject", "body"],
                },
                default_policy={"max_recipients": 5},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.labels.list",
                method="GET",
                google_path="/gmail/v1/users/me/labels",
                description="List all labels in the user's mailbox",
                input_schema={"type": "object", "properties": {}},
                default_policy={},
            ),
        ]


Module = GmailModule