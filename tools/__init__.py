"""
Custom tools for Claude agents.

Define domain-specific tools that Claude can invoke.
Tools are automatically registered with the Agent SDK.

Available Tools:
- extract_structured_data: Extract emails, phone numbers, URLs from text
- query_database: Execute safe SQL queries
- call_external_api: Call REST APIs on whitelisted domains
- browse_web: Automate web browser tasks using headless Chromium
"""

from .custom_tools import (
    extract_structured_data,
    query_database,
    call_external_api,
    browse_web,
)

__all__ = [
    "extract_structured_data",
    "query_database",
    "call_external_api",
    "browse_web",
]
