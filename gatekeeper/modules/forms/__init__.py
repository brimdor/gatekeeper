"""Google Forms module — create, read, and manage Forms and their responses."""

from __future__ import annotations

from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef


class FormsModule(GoogleModule):
    name = "forms"
    display_name = "Google Forms"
    description = "Create, read, and manage Google Forms and their responses"
    icon = "📝"

    required_scopes = [
        "https://www.googleapis.com/auth/forms.body",
        "https://www.googleapis.com/auth/forms.body.readonly",
        "https://www.googleapis.com/auth/forms.responses.readonly",
    ]

    FORMS_BASE = "https://forms.googleapis.com"

    def get_routes(self) -> list[RouteDef]:
        return [
            # ── Forms CRUD ──
            RouteDef(
                route_id="forms.forms.create",
                method="POST",
                base_url=self.FORMS_BASE,
                google_path="/v1/forms",
                description="Create a new Google Form",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title of the new form"},
                        "document_title": {
                            "type": "string",
                            "description": "Document title shown in Drive (defaults to title)",
                        },
                        "unpublished": {
                            "type": "boolean",
                            "description": "If true, the form is not published when created",
                        },
                    },
                },
                query_params=["unpublished"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="forms.forms.get",
                method="GET",
                base_url=self.FORMS_BASE,
                google_path="/v1/forms/{formId}",
                description="Get a Google Form by ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "form_id": {
                            "type": "string",
                            "description": "The ID of the form to retrieve",
                        },
                    },
                    "required": ["form_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="forms.forms.batch_update",
                method="POST",
                base_url=self.FORMS_BASE,
                google_path="/v1/forms/{formId}:batchUpdate",
                description="Apply a batch of updates to a Google Form",
                input_schema={
                    "type": "object",
                    "properties": {
                        "form_id": {
                            "type": "string",
                            "description": "The ID of the form to update",
                        },
                        "requests": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": (
                                "Update request objects for the Forms API batchUpdate endpoint"
                            ),
                        },
                    },
                    "required": ["form_id", "requests"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="forms.forms.set_publish_settings",
                method="POST",
                base_url=self.FORMS_BASE,
                google_path="/v1/forms/{formId}:setPublishSettings",
                description="Update the publish settings of a Google Form",
                input_schema={
                    "type": "object",
                    "properties": {
                        "form_id": {"type": "string", "description": "The ID of the form"},
                        "publish_settings": {
                            "type": "object",
                            "description": "Publish settings (see Forms API reference)",
                        },
                        "update_mask": {
                            "type": "string",
                            "description": "Comma-separated field paths to update",
                        },
                    },
                    "required": ["form_id", "publish_settings"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Responses ──
            RouteDef(
                route_id="forms.forms.responses.get",
                method="GET",
                base_url=self.FORMS_BASE,
                google_path="/v1/forms/{formId}/responses/{responseId}",
                description="Get a single response to a Google Form",
                input_schema={
                    "type": "object",
                    "properties": {
                        "form_id": {"type": "string", "description": "The ID of the form"},
                        "response_id": {"type": "string", "description": "The ID of the response"},
                    },
                    "required": ["form_id", "response_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="forms.forms.responses.list",
                method="GET",
                base_url=self.FORMS_BASE,
                google_path="/v1/forms/{formId}/responses",
                description="List responses to a Google Form",
                input_schema={
                    "type": "object",
                    "properties": {
                        "form_id": {"type": "string", "description": "The ID of the form"},
                        "filter": {
                            "type": "string",
                            "description": "Optional filter expression (e.g., timestamp > ...)",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Maximum number of responses to return",
                            "default": 50,
                        },
                        "page_token": {
                            "type": "string",
                            "description": "Continuation token from a previous list response",
                        },
                    },
                    "required": ["form_id"],
                },
                query_params=["filter", "page_size", "page_token"],
                default_policy={"max_results": 100},
                enabled_by_default=False,
            ),
            # ── Watches ──
            RouteDef(
                route_id="forms.forms.watches.create",
                method="POST",
                base_url=self.FORMS_BASE,
                google_path="/v1/forms/{formId}/watches",
                description="Create a watch on a Google Form (to receive change notifications)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "form_id": {"type": "string", "description": "The ID of the form to watch"},
                        "watch": {
                            "type": "object",
                            "description": "Watch configuration (target event, etc.)",
                        },
                    },
                    "required": ["form_id", "watch"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="forms.forms.watches.delete",
                method="DELETE",
                base_url=self.FORMS_BASE,
                google_path="/v1/forms/{formId}/watches/{watchId}",
                description="Delete a watch on a Google Form",
                input_schema={
                    "type": "object",
                    "properties": {
                        "form_id": {"type": "string", "description": "The ID of the form"},
                        "watch_id": {
                            "type": "string",
                            "description": "The ID of the watch to delete",
                        },
                    },
                    "required": ["form_id", "watch_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="forms.forms.watches.list",
                method="GET",
                base_url=self.FORMS_BASE,
                google_path="/v1/forms/{formId}/watches",
                description="List watches on a Google Form",
                input_schema={
                    "type": "object",
                    "properties": {
                        "form_id": {"type": "string", "description": "The ID of the form"},
                    },
                    "required": ["form_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="forms.forms.watches.renew",
                method="POST",
                base_url=self.FORMS_BASE,
                google_path="/v1/forms/{formId}/watches/{watchId}:renew",
                description="Renew an existing watch on a Google Form (sends an empty body)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "form_id": {"type": "string", "description": "The ID of the form"},
                        "watch_id": {
                            "type": "string",
                            "description": "The ID of the watch to renew",
                        },
                    },
                    "required": ["form_id", "watch_id"],
                },
                # Body must be {} (RenewWatchRequest is an empty schema) — the proxy
                # already sends {} as the JSON body for POST requests with no body
                # params, so no body shape transformation is needed.
                default_policy={},
                enabled_by_default=False,
            ),
        ]


Module = FormsModule
