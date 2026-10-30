# Jira and other input sources

## Option A - Atlassian Rovo MCP server (recommended in Cursor)

OAuth in the browser; no token in files. Either install the Atlassian plugin from the Cursor Marketplace, or add to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "atlassian": { "url": "https://mcp.atlassian.com/v1/mcp/authv2" }
  }
}
```

Then open Cursor Settings -> MCP and click **Connect** on the server. Endpoint names change over time; check Atlassian's "Get started with the Atlassian Rovo MCP Server" page if the URL is rejected. A template lives at `mcp.json.example` in this repo.

After fetching an issue through MCP, save the raw response to `.replication/requirements/<KEY>.raw.json` and run `jira_to_spec.py --json` on it, so every run produces the same normalized file.

## Option B - REST via `jira_to_spec.py`

Environment variables (set in the shell or a git-ignored `.env` that you `source`; never commit them, never paste them into chat):

| Variable | Jira Cloud | Server / Data Center |
| --- | --- | --- |
| `JIRA_BASE_URL` | `https://<site>.atlassian.net` | `https://jira.example.com` |
| `JIRA_EMAIL` | account email | - |
| `JIRA_API_TOKEN` | API token (id.atlassian.com) | - |
| `JIRA_PAT` | - | personal access token (Bearer) |

```bash
python3 scripts/jira_to_spec.py --key ABC-123 --out .replication/requirements
python3 scripts/jira_to_spec.py --key ABC-123 --api 2      # Server/DC or wiki-markup descriptions
python3 scripts/jira_to_spec.py --key ABC-123 --with-links # also fetch linked issues and subtasks (one level)
```

The script calls `GET /rest/api/{3|2}/issue/{key}?expand=names,renderedFields` and `.../comment`. It sends nothing else.

## Option C - offline

- `--json file.json` - REST response, MCP output, or a Jira export of one issue.
- `--text ticket.md` - pasted text, a Word/Confluence page saved as text, or `-` for stdin. Headings like `Acceptance Criteria`, bullet lists and Given/When/Then lines are still detected.

## Other inputs

| Source | How |
| --- | --- |
| Confluence page | Atlassian MCP get-page tool, or user pastes it; add under `## Additional input` |
| Chat instructions | Quote them verbatim under `## Additional input` with `source: chat YYYY-MM-DD` |
| Sample files (CSV, fixed-width, XML, JSON) | Save to `.replication/parity/fixtures/`; record layout in the spec |
| Mapping spreadsheets | Export as CSV; each row becomes a data-format `REQ-` |
| Email / meeting notes | Paste; label `source: email` / `source: meeting` |
