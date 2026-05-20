"""
common.py — Shared helpers for TaxOps GitHub Actions automations.
No LLM. Pure Python + Jira REST API v3 + Slack Web API.
"""
import os
import re
import sys
import requests
from datetime import datetime, timedelta, time as dtime
from base64 import b64encode

import pytz

# ── Environment ───────────────────────────────────────────────────────────────
JIRA_BASE_URL   = os.environ.get("JIRA_BASE_URL", "https://rippling.atlassian.net")
JIRA_EMAIL      = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN  = ********["JIRA_API_TOKEN"]
SLACK_BOT_TOKEN = ********["SLACK_BOT_TOKEN"]

JIRA_PROJECT = "PF"
ISSUE_TYPE   = "Ops - Customer Task"

# Slack channels
CH_OPS   = "C029NNJG8GL"   # Ops Accountability / WFO / Bad Ticket
CH_LEAD  = "C05DL99K1BQ"   # Region Lead Review / QA Alerts
CH_EXEC  = "C03KQHBMMP1"   # Executive Weekly Digest
CH_ERROR = "C05A5MQCRK4"   # Automation Errors

# Slack user-group mentions
MEN_LEADERS = "<!subteam^S06URQSJGEN>"   # @us-taxops-leaders
MEN_LEADS2  = "<!subteam^S0ANS8X2B7Y>"   # secondary leader group (72h escalation)

# Region -> (standard_lead_uid, peo_lead_uid)
REGION_LEADS = {
    "west-region":      ("U03BFEP9614", "U0789C02H6F"),
    "south-region":     ("U04HQQ0TEDN", "U064GL0HC1X"),
    "northeast-region": ("U08J5762KL1", "U04QRLRCK1D"),
    "midwest-region":   ("U02UTR26FML", "U04EJCJ2X1P"),
    "IRS-region":       ("U05U1E7C8H5", "U05U1E7C8H5"),
    "federal-region":   ("U05U1E7C8H5", "U05U1E7C8H5"),
    "pr-region":        ("U04HQQ0TEDN", "U02UTR26FML"),
}

# Optional: Rana's Slack UID for A5 tagging (set as GitHub Secret RANA_SLACK_UID)
RANA_UID = os.environ.get("RANA_SLACK_UID", "")

ET = pytz.timezone("America/New_York")

BASE_JQL = f'project = {JIRA_PROJECT} AND issuetype = "{ISSUE_TYPE}"'


# ── Jira helpers ──────────────────────────────────────────────────────────────

def _jira_headers():
    creds = b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def jira_search(jql, fields=None, max_results=100):
    """Search Jira issues; paginates up to 500 results."""
    url    = f"{JIRA_BASE_URL}/rest/api/3/search"
    params = {"jql": jql, "maxResults": max_results}
    if fields:
        params["fields"] = ",".join(fields)
    r = requests.get(url, headers=_jira_headers(), params=params, timeout=30)
    r.raise_for_status()
    data   = r.json()
    issues = data.get("issues", [])
    total  = data.get("total", 0)
    start  = len(issues)
    while start < total and len(issues) < 500:
        params["startAt"] = start
        r = requests.get(url, headers=_jira_headers(), params=params, timeout=30)
        r.raise_for_status()
        batch = r.json().get("issues", [])
        if not batch:
            break
        issues.extend(batch)
        start += len(batch)
    return issues


def get_comments(issue_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    r   = requests.get(url, headers=_jira_headers(),
                       params={"maxResults": 200}, timeout=30)
    r.raise_for_status()
    return r.json().get("comments", [])


def has_auto_flag(issue_key, flag):
    """Return True if any comment on this issue contains the AUTO_FLAG string."""
    for c in get_comments(issue_key):
        if flag in _adf_to_text(c.get("body", {})):
            return True
    return False


def add_comment(issue_key, text):
    """Add a plain-text comment (wrapped in ADF) to a Jira issue."""
    url  = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    body = {
        "body": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph",
                          "content": [{"type": "text", "text": text}]}]
        }
    }
    r = requests.post(url, headers=_jira_headers(), json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def get_labels(issue):
    return issue.get("fields", {}).get("labels", [])


def update_labels(issue_key, labels):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    r   = requests.put(url, headers=_jira_headers(),
                       json={"fields": {"labels": labels}}, timeout=30)
    r.raise_for_status()


def add_label(issue, issue_key, label):
    current = get_labels(issue)
    if label not in current:
        update_labels(issue_key, current + [label])


def remove_label(issue, issue_key, label):
    current = get_labels(issue)
    if label in current:
        update_labels(issue_key, [l for l in current if l != label])


def remove_labels_matching(issue, issue_key, prefix):
    """Remove all labels that start with the given prefix."""
    current = get_labels(issue)
    cleaned = [l for l in current if not l.startswith(prefix)]
    if len(cleaned) != len(current):
        update_labels(issue_key, cleaned)


def _adf_to_text(node):
    """Recursively extract plain text from an Atlassian Document Format node."""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        return " ".join(_adf_to_text(c) for c in node.get("content", []))
    if isinstance(node, list):
        return " ".join(_adf_to_text(c) for c in node)
    return ""


def desc_text(issue):
    """Return issue description as plain text."""
    raw = issue.get("fields", {}).get("description") or {}
    return _adf_to_text(raw)


def region_lead_uid(labels, is_peo=False):
    """Return the Slack UID of the expected lead for this issue's region label(s)."""
    for lbl, (std, peo) in REGION_LEADS.items():
        if lbl in labels:
            return peo if is_peo else std
    return ""


# ── Slack helpers ─────────────────────────────────────────────────────────────

def _slack_headers():
    return {"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type":  "application/json"}


def slack_post(text, channel):
    """Post a Slack message; return the message timestamp (ts)."""
    r = requests.post("https://slack.com/api/chat.postMessage",
                      headers=_slack_headers(),
                      json={"channel": channel, "text": text}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack postMessage error: {data.get('error')}")
    return data["ts"]


def slack_reply(text, thread_ts, channel):
    """Post a threaded reply; return the reply ts."""
    r = requests.post("https://slack.com/api/chat.postMessage",
                      headers=_slack_headers(),
                      json={"channel": channel, "text": text,
                            "thread_ts": thread_ts}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack reply error: {data.get('error')}")
    return data["ts"]


def post_error(msg):
    """Post to the error channel and stderr."""
    try:
        slack_post(f":rotating_light: *TaxOps Automation Error*\n{msg}", CH_ERROR)
    except Exception:
        pass
    print(f"ERROR: {msg}", file=sys.stderr)


# ── Date / time helpers ───────────────────────────────────────────────────────

def _safe_parse_dt(dt_str):
    """Parse a Jira ISO datetime string to a timezone-aware UTC datetime."""
    if not dt_str:
        return None
    s = re.sub(r"\.\d+", "", dt_str)              # strip sub-seconds
    s = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", s)  # +05:30 -> +0530
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None


def biz_hours_since(dt_str):
    """Business hours elapsed since dt_str (Mon-Fri 9am-6pm ET)."""
    start = _safe_parse_dt(dt_str)
    if not start:
        return 0.0
    now      = datetime.now(pytz.utc)
    start_et = start.astimezone(ET)
    end_et   = now.astimezone(ET)
    if start_et >= end_et:
        return 0.0
    total = 0.0
    cur   = start_et.date()
    while cur <= end_et.date():
        if cur.weekday() < 5:  # Mon-Fri
            day_s = ET.localize(datetime.combine(cur, dtime(9, 0)))
            day_e = ET.localize(datetime.combine(cur, dtime(18, 0)))
            ws    = max(start_et, day_s)
            we    = min(end_et, day_e)
            if we > ws:
                total += (we - ws).total_seconds() / 3600
        cur += timedelta(days=1)
    return total


def biz_days_since(dt_str):
    """Business days (9-hour days) elapsed since dt_str."""
    return biz_hours_since(dt_str) / 9.0


def calendar_hours_since(dt_str):
    """Wall-clock hours elapsed since dt_str."""
    start = _safe_parse_dt(dt_str)
    if not start:
        return 0.0
    return (datetime.now(pytz.utc) - start).total_seconds() / 3600


def issue_url(key):
    return f"{JIRA_BASE_URL}/browse/{key}"


# ── JQL convenience ───────────────────────────────────────────────────────────

COMMON_FIELDS = [
    "summary", "status", "labels", "assignee", "reporter",
    "priority", "created", "updated", "statuscategorychangedate",
]
