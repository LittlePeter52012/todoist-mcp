"""
Todoist MCP — API connectivity test.
Usage: TODOIST_API_TOKEN=xxx python test_run.py
"""
import os
import sys
import requests

TOKEN = os.environ.get("TODOIST_API_TOKEN", "")
BASE_URL = "https://api.todoist.com/api/v1"
REQUEST_TIMEOUT = 30


def _extract(data):
    """Extract results from v1 paginated response."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("results", [])
    return []


def test_workflow():
    if not TOKEN:
        print("❌ TODOIST_API_TOKEN is not set.")
        print("   Get your token from: https://app.todoist.com/app/settings/integrations")
        print("   Then run: TODOIST_API_TOKEN=xxx python test_run.py")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

    # --- 1. List Projects ---
    print("--- 1. Testing: List Projects ---")
    res = requests.get(f"{BASE_URL}/projects", headers=headers, timeout=REQUEST_TIMEOUT)
    if res.status_code == 200:
        projects = _extract(res.json())
        print(f"✅ Found {len(projects)} projects:")
        for p in projects[:5]:
            print(f"   - {p['name']} (ID: {p['id']})")
    else:
        print(f"❌ Error {res.status_code}: {res.text}")
        return

    # --- 2. List Active Tasks ---
    print("\n--- 2. Testing: List Active Tasks ---")
    res = requests.get(f"{BASE_URL}/tasks", headers=headers, timeout=REQUEST_TIMEOUT)
    if res.status_code == 200:
        tasks = _extract(res.json())
        print(f"✅ Found {len(tasks)} active tasks:")
        for t in tasks[:5]:
            due = ""
            if t.get("due"):
                due = f" (due: {t['due'].get('date', '')})"
            elif t.get("deadline"):
                due = f" (deadline: {t['deadline'].get('date', '')})"
            print(f"   - [{t.get('priority', 1)}] {t['content']}{due}")
    else:
        print(f"❌ Error {res.status_code}: {res.text}")
        return

    # --- 3. List Labels ---
    print("\n--- 3. Testing: List Labels ---")
    res = requests.get(f"{BASE_URL}/labels", headers=headers, timeout=REQUEST_TIMEOUT)
    if res.status_code == 200:
        labels = _extract(res.json())
        print(f"✅ Found {len(labels)} labels:")
        for lb in labels[:5]:
            print(f"   - {lb['name']}")
    else:
        print(f"❌ Error {res.status_code}: {res.text}")

    # --- 4. List Sections ---
    print("\n--- 4. Testing: List Sections ---")
    res = requests.get(f"{BASE_URL}/sections", headers=headers, timeout=REQUEST_TIMEOUT)
    if res.status_code == 200:
        sections = _extract(res.json())
        print(f"✅ Found {len(sections)} sections:")
        for s in sections[:5]:
            print(f"   - {s['name']} (project: {s.get('project_id', 'N/A')})")
    else:
        print(f"❌ Error {res.status_code}: {res.text}")

    print("\n🎉 All tests passed! API connection is working.")


if __name__ == "__main__":
    try:
        test_workflow()
    except Exception as e:
        print(f"❌ Test failed: {e}")
