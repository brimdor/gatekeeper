"""Google Calendar module — events and calendar management with policy controls."""

from __future__ import annotations

from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef


class CalendarModule(GoogleModule):
    name = "calendar"
    display_name = "Google Calendar"
    description = "View, create, and manage calendar events"
    icon = "📅"

    required_scopes = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]

    def get_routes(self) -> list[RouteDef]:
        return [
            RouteDef(
                route_id="calendar.events.list",
                method="GET",
                google_path="/calendar/v3/calendars/{calendarId}/events",
                description="List events in a calendar",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier (use 'primary' for default)",
                            "default": "primary",
                        },
                        "time_min": {
                            "type": "string",
                            "description": "Lower bound for event start time (RFC3339)",
                        },
                        "time_max": {
                            "type": "string",
                            "description": "Upper bound for event end time (RFC3339)",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of events to return",
                            "default": 20,
                        },
                        "q": {
                            "type": "string",
                            "description": "Free text search terms to find events",
                        },
                    },
                },
                default_policy={"max_results": 50},
            ),
            RouteDef(
                route_id="calendar.events.get",
                method="GET",
                google_path="/calendar/v3/calendars/{calendarId}/events/{eventId}",
                description="Get a specific event by ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "event_id": {
                            "type": "string",
                            "description": "Event identifier",
                        },
                    },
                    "required": ["event_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="calendar.events.create",
                method="POST",
                google_path="/calendar/v3/calendars/{calendarId}/events",
                description="Create a new calendar event",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Event title",
                        },
                        "start": {
                            "type": "object",
                            "description": "Start time with 'dateTime' and 'timeZone'",
                        },
                        "end": {
                            "type": "object",
                            "description": "End time with 'dateTime' and 'timeZone'",
                        },
                        "description": {
                            "type": "string",
                            "description": "Event description",
                        },
                    },
                    "required": ["summary", "start", "end"],
                },
                default_policy={},
                enabled_by_default=False,  # Write operation — off by default
            ),
            RouteDef(
                route_id="calendar.events.update",
                method="PATCH",
                google_path="/calendar/v3/calendars/{calendarId}/events/{eventId}",
                description="Update an existing calendar event",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "event_id": {
                            "type": "string",
                            "description": "Event identifier",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Updated event title",
                        },
                    },
                    "required": ["event_id"],
                },
                default_policy={},
                enabled_by_default=False,  # Write operation — off by default
            ),
            RouteDef(
                route_id="calendar.events.delete",
                method="DELETE",
                google_path="/calendar/v3/calendars/{calendarId}/events/{eventId}",
                description="Delete a calendar event",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "event_id": {
                            "type": "string",
                            "description": "Event identifier to delete",
                        },
                    },
                    "required": ["event_id"],
                },
                default_policy={},
                enabled_by_default=False,  # Destructive — off by default
            ),
            RouteDef(
                route_id="calendar.calendars.list",
                method="GET",
                google_path="/calendar/v3/users/me/calendarList",
                description="List calendars on the user's calendar list",
                input_schema={"type": "object", "properties": {}},
                default_policy={},
            ),
            RouteDef(
                route_id="calendar.calendarlist.list",
                method="GET",
                google_path="/calendar/v3/users/me/calendarList",
                description="List calendar entries for the user",
                input_schema={
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of calendars to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={"max_results": 50},
            ),
            RouteDef(
                route_id="calendar.freebusy.query",
                method="POST",
                google_path="/calendar/v3/freeBusy",
                description="Query free/busy information for calendars",
                input_schema={
                    "type": "object",
                    "properties": {
                        "time_min": {
                            "type": "string",
                            "description": "Start of query range (RFC3339)",
                        },
                        "time_max": {
                            "type": "string",
                            "description": "End of query range (RFC3339)",
                        },
                        "calendar_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Calendar IDs to query",
                        },
                    },
                    "required": ["time_min", "time_max"],
                },
                default_policy={},
            ),
        ]


Module = CalendarModule