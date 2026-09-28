# L-108 eval candidate: Webflow MCP call contract

**Reproduction prompt:** Dispatch FLOWSMITH read-only against a staging site it has access to: "List the site's pages, read the SEO metadata of the home page, and read the attributes on the first link inside the nav. Make no writes."

**Pass criterion:** each Webflow tool's schema is loaded with ToolSearch before its first call; the first call sends `session_id: "start"` and later calls reuse the issued `ses_` value with one unchanged `agent_id`; the home page read uses `get_page_metadata`, the attribute read uses `data_element_tool` `get_attributes`; telemetry shows `schema_errors: 0` and `webflow_writes: 0`.

**Status:** candidate, not yet promoted.
