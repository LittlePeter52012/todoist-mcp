"""
Todoist MCP Server v1.2.0
Connect AI agents to your Todoist tasks via the Todoist API v1 (unified).

New in v1.2.0:
- 🚚 move_task: Move tasks across projects, sections, or under parent tasks
- 🔍 move_task_by_name: Move tasks by name (fuzzy matching)
- 📊 get_project_overview: Get a full overview of all projects, sections, and task counts
- 🏗️ update_section: Rename sections
- ⚡ Enhanced update_task: Now supports assignee_id, duration, deadline_date, due_datetime
- 🐛 Fixed API token validation to support all Todoist token formats
"""
import os
import sys
import json
import uuid
import re
import requests

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("Error: 'mcp' package is not installed. Please install it with: pip install 'mcp[cli]'")
    sys.exit(1)

# ─── Initialize FastMCP Server ───
mcp = FastMCP("todoist")

# ╔═══════════════════════════════════════════════════════════════╗
# ║  🔑  API TOKEN 通过环境变量 TODOIST_API_TOKEN 传入           ║
# ║  在 MCP 配置文件（如 settings.json）的 env 中设置即可        ║
# ║  获取地址: https://app.todoist.com/app/settings/integrations ║
# ╚═══════════════════════════════════════════════════════════════╝

# ─── Other Configuration ───
BASE_URL = "https://api.todoist.com/api/v1"
REQUEST_TIMEOUT = 30  # seconds — prevent hanging on network issues


def _get_token() -> str:
    """
    Retrieve the Todoist API token from the TODOIST_API_TOKEN environment variable.
    This is set in the MCP config file (e.g. ~/.gemini/settings.json).
    """
    token = os.environ.get("TODOIST_API_TOKEN", "")
    if not token:
        raise ValueError(
            "TODOIST_API_TOKEN environment variable is not set. "
            "Please set it in your MCP config (e.g. settings.json > mcpServers > todoist > env). "
            "Get your token from: https://app.todoist.com/app/settings/integrations"
        )
    return token


def _headers() -> dict:
    """Standard headers for Todoist API calls."""
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
        "X-Request-Id": str(uuid.uuid4()),
    }


def _extract_results(response_json) -> list:
    """
    Extract results from API response.
    v1 API returns paginated: {"results": [...], "next_cursor": ...}
    """
    if isinstance(response_json, list):
        return response_json
    if isinstance(response_json, dict):
        return response_json.get("results", [])
    return []


def _fmt_due(due: dict | None, deadline: dict | None = None) -> str:
    """Format due-date and deadline objects into a readable string."""
    parts = []
    if due:
        if due.get("datetime"):
            parts.append(due["datetime"])
        elif due.get("date"):
            parts.append(due["date"])
        if due.get("is_recurring"):
            parts.append("🔁 recurring")
        if due.get("string"):
            parts.append(f"({due['string']})")
    if deadline:
        dl_date = deadline.get("date", "")
        if dl_date:
            parts.append(f"⏰ deadline: {dl_date}")
    return " ".join(parts)


def _fmt_task(t: dict) -> str:
    """Format a single task dict into a readable line."""
    pri_map = {4: "🔴", 3: "🟠", 2: "🔵", 1: "⚪"}
    pri = pri_map.get(t.get("priority", 1), "⚪")
    due = _fmt_due(t.get("due"), t.get("deadline"))
    labels = ", ".join(t.get("labels", []))
    checked = "✅ " if t.get("checked") else ""
    parts = [
        f"{pri} {checked}[{t.get('id')}] {t.get('content', '(no content)')}",
    ]
    if t.get("description"):
        parts.append(f"  📝 {t['description']}")
    if due:
        parts.append(f"  📅 {due}")
    if labels:
        parts.append(f"  🏷️ {labels}")
    if t.get("project_id"):
        parts.append(f"  📂 Project: {t['project_id']}")
    if t.get("section_id"):
        parts.append(f"  📑 Section: {t['section_id']}")
    return "\n".join(parts)


# ═══════════════════════════════════════════════
#  Projects
# ═══════════════════════════════════════════════

@mcp.tool()
def list_projects() -> str:
    """
    List all projects in the user's Todoist account.
    Returns project names, IDs, and colors.
    """
    try:
        res = requests.get(f"{BASE_URL}/projects", headers=_headers(), timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        projects = _extract_results(res.json())
        if not projects:
            return "No projects found."
        lines = []
        for p in projects:
            fav = "⭐ " if p.get("is_favorite") else ""
            inbox = " (Inbox)" if p.get("inbox_project") else ""
            parent = f"  ↳ parent: {p['parent_id']}" if p.get("parent_id") else ""
            lines.append(f"- {fav}{p['name']}{inbox}  (ID: {p['id']}, color: {p.get('color', 'default')}){parent}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing projects: {e}"


@mcp.tool()
def create_project(name: str, color: str = "", parent_id: str = "") -> str:
    """
    Create a new project.

    Args:
        name: Name of the project.
        color: Optional color (e.g. 'berry_red', 'blue', 'charcoal').
        parent_id: Optional parent project ID to create as a sub-project.
    """
    body: dict = {"name": name}
    if color:
        body["color"] = color
    if parent_id:
        body["parent_id"] = parent_id
    try:
        res = requests.post(f"{BASE_URL}/projects", headers=_headers(), json=body, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        p = res.json()
        return f"✅ Project created: '{p['name']}' (ID: {p['id']})"
    except Exception as e:
        return f"Error creating project: {e}"


@mcp.tool()
def update_project(project_id: str, name: str = "", color: str = "", is_favorite: bool = False) -> str:
    """
    Update an existing project.

    Args:
        project_id: ID of the project to update.
        name: New name for the project.
        color: New color for the project.
        is_favorite: Whether to mark as favorite.
    """
    body: dict = {}
    if name:
        body["name"] = name
    if color:
        body["color"] = color
    if is_favorite:
        body["is_favorite"] = True
    if not body:
        return "Nothing to update. Provide at least one of: name, color, is_favorite."
    try:
        res = requests.post(f"{BASE_URL}/projects/{project_id}", headers=_headers(), json=body, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        p = res.json()
        return f"✅ Project updated: '{p['name']}' (ID: {p['id']})"
    except Exception as e:
        return f"Error updating project: {e}"


@mcp.tool()
def delete_project(project_id: str) -> str:
    """
    Delete a project and all its tasks.

    Args:
        project_id: ID of the project to delete.
    """
    try:
        res = requests.delete(f"{BASE_URL}/projects/{project_id}", headers=_headers(), timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return f"✅ Project {project_id} deleted."
    except Exception as e:
        return f"Error deleting project: {e}"


@mcp.tool()
def get_project_overview() -> str:
    """
    Get a comprehensive overview of all projects with their sections and task counts.
    Useful for understanding the full project structure before organizing tasks.
    """
    try:
        headers = _headers()

        # Get all projects
        res = requests.get(f"{BASE_URL}/projects", headers=headers, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        projects = _extract_results(res.json())

        if not projects:
            return "No projects found."

        # Get all sections
        res_sec = requests.get(f"{BASE_URL}/sections", headers=headers, timeout=REQUEST_TIMEOUT)
        res_sec.raise_for_status()
        sections = _extract_results(res_sec.json())

        # Group sections by project
        sec_by_project: dict = {}
        for s in sections:
            pid = s.get("project_id", "")
            if pid not in sec_by_project:
                sec_by_project[pid] = []
            sec_by_project[pid].append(s)

        # Build overview
        lines = ["📊 **Project Overview**\n"]
        for p in projects:
            fav = "⭐ " if p.get("is_favorite") else ""
            inbox = " (Inbox)" if p.get("inbox_project") else ""
            indent = "  " if p.get("parent_id") else ""
            lines.append(f"{indent}📁 {fav}**{p['name']}**{inbox}  (ID: {p['id']})")

            proj_sections = sec_by_project.get(p["id"], [])
            for s in proj_sections:
                lines.append(f"{indent}  📑 {s['name']}  (ID: {s['id']})")

        return "\n".join(lines)
    except Exception as e:
        return f"Error getting project overview: {e}"


# ═══════════════════════════════════════════════
#  Tasks
# ═══════════════════════════════════════════════

@mcp.tool()
def get_tasks(project_id: str = "", label: str = "", filter_str: str = "") -> str:
    """
    Get all active tasks. Can filter by project, label, or Todoist filter string.

    Args:
        project_id: Optional project ID to filter tasks by.
        label: Optional label name to filter tasks by.
        filter_str: Optional Todoist filter string (e.g. 'today', 'overdue', 'p1').
    """
    params: dict = {}
    if project_id:
        params["project_id"] = project_id
    if label:
        params["label"] = label
    if filter_str:
        params["filter"] = filter_str
    try:
        res = requests.get(f"{BASE_URL}/tasks", headers=_headers(), params=params, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        tasks = _extract_results(res.json())
        if not tasks:
            return "No active tasks found."
        return "\n\n".join(_fmt_task(t) for t in tasks)
    except Exception as e:
        return f"Error getting tasks: {e}"


@mcp.tool()
def get_task(task_id: str) -> str:
    """
    Get detailed information about a single task.

    Args:
        task_id: ID of the task.
    """
    try:
        res = requests.get(f"{BASE_URL}/tasks/{task_id}", headers=_headers(), timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        t = res.json()
        lines = [_fmt_task(t)]
        if t.get("parent_id"):
            lines.append(f"  🔗 Parent: {t['parent_id']}")
        lines.append(f"  💬 Notes: {t.get('note_count', 0)}")
        lines.append(f"  📆 Created: {t.get('added_at', 'N/A')}")
        if t.get("duration"):
            lines.append(f"  ⏱️ Duration: {t['duration']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error getting task: {e}"


@mcp.tool()
def create_task(
    content: str,
    description: str = "",
    project_id: str = "",
    section_id: str = "",
    parent_id: str = "",
    due_string: str = "",
    due_date: str = "",
    priority: int = 1,
    labels: str = "",
) -> str:
    """
    Create a new task in Todoist.

    Args:
        content: The task title/content (required).
        description: Optional description text.
        project_id: Optional project ID to add the task to.
        section_id: Optional section ID within a project.
        parent_id: Optional parent task ID (for sub-tasks).
        due_string: Optional due date in natural language (e.g. 'tomorrow', 'every monday', 'Jan 23').
        due_date: Optional due date in YYYY-MM-DD format.
        priority: Priority from 1 (normal) to 4 (urgent). Default is 1.
        labels: Optional comma-separated label names (e.g. 'work,urgent').
    """
    body: dict = {"content": content}
    if description:
        body["description"] = description
    if project_id:
        body["project_id"] = project_id
    if section_id:
        body["section_id"] = section_id
    if parent_id:
        body["parent_id"] = parent_id
    if due_string:
        body["due_string"] = due_string
    if due_date:
        body["due_date"] = due_date
    if priority and priority != 1:
        body["priority"] = priority
    if labels:
        body["labels"] = [l.strip() for l in labels.split(",")]
    try:
        res = requests.post(f"{BASE_URL}/tasks", headers=_headers(), json=body, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        t = res.json()
        return f"✅ Task created: '{t['content']}' (ID: {t['id']})\n{_fmt_task(t)}"
    except Exception as e:
        return f"Error creating task: {e}"


@mcp.tool()
def update_task(
    task_id: str,
    content: str = "",
    description: str = "",
    due_string: str = "",
    due_date: str = "",
    due_datetime: str = "",
    priority: int = 0,
    labels: str = "",
    assignee_id: str = "",
    duration: int = 0,
    duration_unit: str = "",
    deadline_date: str = "",
) -> str:
    """
    Update an existing task.

    Args:
        task_id: ID of the task to update (required).
        content: New task title/content.
        description: New description.
        due_string: New due date in natural language.
        due_date: New due date in YYYY-MM-DD format.
        due_datetime: New due date and time in RFC3339 format.
        priority: New priority (1-4).
        labels: New comma-separated label names (replaces existing labels).
        assignee_id: ID of user to assign the task to.
        duration: Task duration in minutes or days (requires duration_unit).
        duration_unit: Unit for duration: 'minute' or 'day'.
        deadline_date: Deadline date in YYYY-MM-DD format.
    """
    body: dict = {}
    if content:
        body["content"] = content
    if description:
        body["description"] = description
    if due_string:
        body["due_string"] = due_string
    if due_date:
        body["due_date"] = due_date
    if due_datetime:
        body["due_datetime"] = due_datetime
    if priority:
        body["priority"] = priority
    if labels:
        body["labels"] = [l.strip() for l in labels.split(",")]
    if assignee_id:
        body["assignee_id"] = assignee_id
    if duration:
        body["duration"] = duration
    if duration_unit:
        body["duration_unit"] = duration_unit
    if deadline_date:
        body["deadline_date"] = deadline_date
    if not body:
        return "Nothing to update. Provide at least one field."
    try:
        res = requests.post(f"{BASE_URL}/tasks/{task_id}", headers=_headers(), json=body, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        t = res.json()
        return f"✅ Task updated: '{t['content']}' (ID: {t['id']})\n{_fmt_task(t)}"
    except Exception as e:
        return f"Error updating task: {e}"


@mcp.tool()
def move_task(
    task_id: str,
    project_id: str = "",
    section_id: str = "",
    parent_id: str = "",
) -> str:
    """
    Move a task to a different project, section, or under a parent task.
    This enables cross-project task organization.

    Args:
        task_id: ID of the task to move (required).
        project_id: ID of the target project to move the task to.
        section_id: ID of the target section to move the task to.
        parent_id: ID of the parent task to move the task under.
    """
    body: dict = {}
    if project_id:
        body["project_id"] = project_id
    if section_id:
        body["section_id"] = section_id
    if parent_id:
        body["parent_id"] = parent_id
    if not body:
        return "Nothing to move. Provide at least one of: project_id, section_id, parent_id."
    try:
        res = requests.post(
            f"{BASE_URL}/tasks/{task_id}/move",
            headers=_headers(),
            json=body,
            timeout=REQUEST_TIMEOUT,
        )
        res.raise_for_status()
        t = res.json()
        dest_parts = []
        if project_id:
            dest_parts.append(f"project {project_id}")
        if section_id:
            dest_parts.append(f"section {section_id}")
        if parent_id:
            dest_parts.append(f"parent {parent_id}")
        return f"✅ Task moved to {', '.join(dest_parts)}: '{t.get('content', '')}' (ID: {t.get('id', task_id)})\n{_fmt_task(t)}"
    except Exception as e:
        return f"Error moving task: {e}"


@mcp.tool()
def close_task(task_id: str) -> str:
    """
    Close (complete) a task.

    Args:
        task_id: ID of the task to close.
    """
    try:
        res = requests.post(f"{BASE_URL}/tasks/{task_id}/close", headers=_headers(), timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return f"✅ Task {task_id} completed."
    except Exception as e:
        return f"Error closing task: {e}"


@mcp.tool()
def reopen_task(task_id: str) -> str:
    """
    Reopen a previously completed task.

    Args:
        task_id: ID of the task to reopen.
    """
    try:
        res = requests.post(f"{BASE_URL}/tasks/{task_id}/reopen", headers=_headers(), timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return f"✅ Task {task_id} reopened."
    except Exception as e:
        return f"Error reopening task: {e}"


@mcp.tool()
def delete_task(task_id: str) -> str:
    """
    Permanently delete a task.

    Args:
        task_id: ID of the task to delete.
    """
    try:
        res = requests.delete(f"{BASE_URL}/tasks/{task_id}", headers=_headers(), timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return f"✅ Task {task_id} deleted."
    except Exception as e:
        return f"Error deleting task: {e}"


# ═══════════════════════════════════════════════
#  Sections
# ═══════════════════════════════════════════════

@mcp.tool()
def list_sections(project_id: str = "") -> str:
    """
    List sections, optionally filtered by project.

    Args:
        project_id: Optional project ID to filter sections by.
    """
    params: dict = {}
    if project_id:
        params["project_id"] = project_id
    try:
        res = requests.get(f"{BASE_URL}/sections", headers=_headers(), params=params, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        sections = _extract_results(res.json())
        if not sections:
            return "No sections found."
        lines = []
        for s in sections:
            lines.append(f"- {s['name']}  (ID: {s['id']}, project: {s.get('project_id', 'N/A')})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing sections: {e}"


@mcp.tool()
def create_section(name: str, project_id: str) -> str:
    """
    Create a new section within a project.

    Args:
        name: Name of the section.
        project_id: ID of the project to create the section in.
    """
    body = {"name": name, "project_id": project_id}
    try:
        res = requests.post(f"{BASE_URL}/sections", headers=_headers(), json=body, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        s = res.json()
        return f"✅ Section created: '{s['name']}' (ID: {s['id']})"
    except Exception as e:
        return f"Error creating section: {e}"


@mcp.tool()
def update_section(section_id: str, name: str) -> str:
    """
    Rename an existing section.

    Args:
        section_id: ID of the section to update.
        name: New name for the section.
    """
    body = {"name": name}
    try:
        res = requests.post(f"{BASE_URL}/sections/{section_id}", headers=_headers(), json=body, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        s = res.json()
        return f"✅ Section updated: '{s['name']}' (ID: {s['id']})"
    except Exception as e:
        return f"Error updating section: {e}"


@mcp.tool()
def delete_section(section_id: str) -> str:
    """
    Delete a section and move its tasks to the parent project.

    Args:
        section_id: ID of the section to delete.
    """
    try:
        res = requests.delete(f"{BASE_URL}/sections/{section_id}", headers=_headers(), timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return f"✅ Section {section_id} deleted."
    except Exception as e:
        return f"Error deleting section: {e}"


# ═══════════════════════════════════════════════
#  Labels
# ═══════════════════════════════════════════════

@mcp.tool()
def list_labels() -> str:
    """
    List all personal labels in the user's Todoist account.
    """
    try:
        res = requests.get(f"{BASE_URL}/labels", headers=_headers(), timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        labels = _extract_results(res.json())
        if not labels:
            return "No labels found."
        lines = []
        for lb in labels:
            fav = "⭐ " if lb.get("is_favorite") else ""
            lines.append(f"- {fav}{lb['name']}  (ID: {lb['id']}, color: {lb.get('color', 'default')})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing labels: {e}"


@mcp.tool()
def create_label(name: str, color: str = "") -> str:
    """
    Create a new personal label.

    Args:
        name: Name of the label.
        color: Optional color (e.g. 'berry_red', 'blue', 'charcoal').
    """
    body: dict = {"name": name}
    if color:
        body["color"] = color
    try:
        res = requests.post(f"{BASE_URL}/labels", headers=_headers(), json=body, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        lb = res.json()
        return f"✅ Label created: '{lb['name']}' (ID: {lb['id']})"
    except Exception as e:
        return f"Error creating label: {e}"


# ═══════════════════════════════════════════════
#  Comments
# ═══════════════════════════════════════════════

@mcp.tool()
def get_comments(task_id: str = "", project_id: str = "") -> str:
    """
    Get comments for a task or project. Must provide either task_id or project_id.

    Args:
        task_id: ID of the task to get comments for.
        project_id: ID of the project to get comments for.
    """
    if not task_id and not project_id:
        return "Error: must provide either task_id or project_id."
    params: dict = {}
    if task_id:
        params["task_id"] = task_id
    if project_id:
        params["project_id"] = project_id
    try:
        res = requests.get(f"{BASE_URL}/comments", headers=_headers(), params=params, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        comments = _extract_results(res.json())
        if not comments:
            return "No comments found."
        lines = []
        for c in comments:
            lines.append(f"- [{c.get('id')}] {c.get('content', '')}  ({c.get('posted_at', '')})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error getting comments: {e}"


@mcp.tool()
def create_comment(content: str, task_id: str = "", project_id: str = "") -> str:
    """
    Add a comment to a task or project. Must provide either task_id or project_id.

    Args:
        content: The comment text.
        task_id: ID of the task to comment on.
        project_id: ID of the project to comment on.
    """
    if not task_id and not project_id:
        return "Error: must provide either task_id or project_id."
    body: dict = {"content": content}
    if task_id:
        body["task_id"] = task_id
    if project_id:
        body["project_id"] = project_id
    try:
        res = requests.post(f"{BASE_URL}/comments", headers=_headers(), json=body, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        c = res.json()
        return f"✅ Comment added (ID: {c['id']}): {c['content']}"
    except Exception as e:
        return f"Error creating comment: {e}"


# ═══════════════════════════════════════════════
#  Smart Name-Based Operations (模糊搜索)
# ═══════════════════════════════════════════════

def _get_all_tasks() -> list:
    """Fetch all active tasks (handles pagination)."""
    all_tasks = []
    headers = _headers()
    cursor = None
    while True:
        params: dict = {}
        if cursor:
            params["cursor"] = cursor
        res = requests.get(f"{BASE_URL}/tasks", headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        data = res.json()
        if isinstance(data, list):
            all_tasks.extend(data)
            break
        results = data.get("results", [])
        all_tasks.extend(results)
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return all_tasks


def _find_tasks_by_name(query: str) -> list:
    """Find tasks whose content contains the query string (case-insensitive)."""
    tasks = _get_all_tasks()
    q = query.lower()
    return [t for t in tasks if q in t.get("content", "").lower()]


@mcp.tool()
def search_task_by_name(query: str) -> str:
    """
    Search for tasks by name using partial/fuzzy matching.
    Returns all tasks whose title contains the search query.

    Args:
        query: Search keyword to match against task titles (case-insensitive).
    """
    try:
        matches = _find_tasks_by_name(query)
        if not matches:
            return f"No tasks found matching '{query}'."
        lines = [f"Found {len(matches)} task(s) matching '{query}':\n"]
        for t in matches:
            lines.append(_fmt_task(t))
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching tasks: {e}"


@mcp.tool()
def complete_task_by_name(task_name: str) -> str:
    """
    Complete a task by searching for it by name. Uses partial name matching.
    If multiple tasks match, lists them for the user to choose.

    Args:
        task_name: Name/content of the task to find and complete.
    """
    try:
        matches = _find_tasks_by_name(task_name)
        if not matches:
            return f"❌ No task found matching '{task_name}'."
        if len(matches) > 1:
            lines = [f"⚠️ Found {len(matches)} tasks matching '{task_name}'. Please be more specific or use the task ID:\n"]
            for t in matches:
                lines.append(_fmt_task(t))
                lines.append("")
            return "\n".join(lines)
        task = matches[0]
        res = requests.post(f"{BASE_URL}/tasks/{task['id']}/close", headers=_headers())
        res.raise_for_status()
        return f"✅ Task completed: '{task['content']}' (ID: {task['id']})"
    except Exception as e:
        return f"Error completing task: {e}"


@mcp.tool()
def delete_task_by_name(task_name: str) -> str:
    """
    Delete a task by searching for it by name. Uses partial name matching.
    If multiple tasks match, lists them for the user to choose.

    Args:
        task_name: Name/content of the task to find and delete.
    """
    try:
        matches = _find_tasks_by_name(task_name)
        if not matches:
            return f"❌ No task found matching '{task_name}'."
        if len(matches) > 1:
            lines = [f"⚠️ Found {len(matches)} tasks matching '{task_name}'. Please be more specific or use the task ID:\n"]
            for t in matches:
                lines.append(_fmt_task(t))
                lines.append("")
            return "\n".join(lines)
        task = matches[0]
        res = requests.delete(f"{BASE_URL}/tasks/{task['id']}", headers=_headers())
        res.raise_for_status()
        return f"✅ Task deleted: '{task['content']}' (ID: {task['id']})"
    except Exception as e:
        return f"Error deleting task: {e}"


@mcp.tool()
def update_task_by_name(
    task_name: str,
    content: str = "",
    description: str = "",
    due_string: str = "",
    priority: int = 0,
) -> str:
    """
    Update a task by searching for it by name. Uses partial name matching.
    If multiple tasks match, lists them for the user to choose.

    Args:
        task_name: Name/content of the task to find and update.
        content: New task title.
        description: New description.
        due_string: New due date in natural language (e.g. 'tomorrow', 'next Monday').
        priority: New priority (1-4).
    """
    try:
        matches = _find_tasks_by_name(task_name)
        if not matches:
            return f"❌ No task found matching '{task_name}'."
        if len(matches) > 1:
            lines = [f"⚠️ Found {len(matches)} tasks matching '{task_name}'. Please be more specific or use the task ID:\n"]
            for t in matches:
                lines.append(_fmt_task(t))
                lines.append("")
            return "\n".join(lines)
        task = matches[0]
        body: dict = {}
        if content:
            body["content"] = content
        if description:
            body["description"] = description
        if due_string:
            body["due_string"] = due_string
        if priority:
            body["priority"] = priority
        if not body:
            return "Nothing to update. Provide at least one of: content, description, due_string, priority."
        res = requests.post(f"{BASE_URL}/tasks/{task['id']}", headers=_headers(), json=body)
        res.raise_for_status()
        t = res.json()
        return f"✅ Task updated: '{t['content']}' (ID: {t['id']})\n{_fmt_task(t)}"
    except Exception as e:
        return f"Error updating task: {e}"


@mcp.tool()
def move_task_by_name(
    task_name: str,
    project_id: str = "",
    section_id: str = "",
    parent_id: str = "",
) -> str:
    """
    Move a task to a different project/section by searching for it by name.
    Uses partial name matching. If multiple tasks match, lists them for the user to choose.

    Args:
        task_name: Name/content of the task to find and move.
        project_id: ID of the target project to move the task to.
        section_id: ID of the target section to move the task to.
        parent_id: ID of the parent task to move the task under.
    """
    if not project_id and not section_id and not parent_id:
        return "Nothing to move. Provide at least one of: project_id, section_id, parent_id."
    try:
        matches = _find_tasks_by_name(task_name)
        if not matches:
            return f"❌ No task found matching '{task_name}'."
        if len(matches) > 1:
            lines = [f"⚠️ Found {len(matches)} tasks matching '{task_name}'. Please be more specific or use the task ID:\n"]
            for t in matches:
                lines.append(_fmt_task(t))
                lines.append("")
            return "\n".join(lines)
        task = matches[0]
        body: dict = {}
        if project_id:
            body["project_id"] = project_id
        if section_id:
            body["section_id"] = section_id
        if parent_id:
            body["parent_id"] = parent_id
        res = requests.post(
            f"{BASE_URL}/tasks/{task['id']}/move",
            headers=_headers(),
            json=body,
            timeout=REQUEST_TIMEOUT,
        )
        res.raise_for_status()
        t = res.json()
        dest_parts = []
        if project_id:
            dest_parts.append(f"project {project_id}")
        if section_id:
            dest_parts.append(f"section {section_id}")
        if parent_id:
            dest_parts.append(f"parent {parent_id}")
        return f"✅ Task moved to {', '.join(dest_parts)}: '{t.get('content', '')}' (ID: {t.get('id', task['id'])})\n{_fmt_task(t)}"
    except Exception as e:
        return f"Error moving task: {e}"


# ═══════════════════════════════════════════════
#  Configuration (API Token)
# ═══════════════════════════════════════════════

@mcp.tool()
def set_api_token(token: str) -> str:
    """
    Set or update the Todoist API Token at runtime.
    This allows switching accounts without restarting the server.
    The token will persist for the current session only.

    Args:
        token: Your Todoist API Token (get from https://app.todoist.com/app/settings/integrations).
    """
    token = token.strip()
    if not token or len(token) < 10:
        return "❌ Invalid token. Please provide a valid Todoist API Token."
    os.environ["TODOIST_API_TOKEN"] = token
    # Verify the token works
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        res = requests.get(f"{BASE_URL}/projects", headers=headers, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        projects = _extract_results(res.json())
        return f"✅ API Token set successfully! Found {len(projects)} projects. Token is active for this session."
    except Exception as e:
        os.environ.pop("TODOIST_API_TOKEN", None)
        return f"❌ Token verification failed: {e}. Token was not saved."


@mcp.tool()
def get_current_config() -> str:
    """
    Show the current configuration status (whether API token is set, API base URL, etc).
    """
    token = os.environ.get("TODOIST_API_TOKEN", "")
    token_status = f"✅ Set (ending in ...{token[-4:]})" if len(token) >= 4 else ("⚠️ Set (too short)" if token else "❌ Not set")
    return (
        f"🔧 Todoist MCP Configuration\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  API Token:  {token_status}\n"
        f"  API URL:    {BASE_URL}\n"
        f"  Version:    1.2.0\n"
        f"  Get token:  https://app.todoist.com/app/settings/integrations"
    )


# ═══════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════

def main():
    mcp.run()


if __name__ == "__main__":
    main()
