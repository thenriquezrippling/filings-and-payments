# -*- coding: utf-8 -*-
"""
common.py -- Shared helpers for TaxOps GitHub Actions automations.
No LLM. Pure Python + Jira REST API v3 + Slack Workflow Builder webhooks.
"""
import os
import re
import sys
import requests
from datetime import datetime, timedelta, time as dtime
from base64 import b64encode

import pytz


def _require(name):
    """Get a required environment variable or exit with a clear error."""
    val = os.getenv(name, "")
    if not val:
        print(f"FATAL: required env var {name!r} is not set", file=sys.stderr)
        sys.exit(1)
    return val


# -- Config -------------------------------------------------------------------
JIRA_BASE_URL      = os.getenv("JIRA_BASE_URL", "https://rippling.atlassian.net")
JIRA_EMAIL         = _require("JIRA_EMAIL")
JIRA_API_TOKEN     = _require("JIRA_API_TOKEN")
SLACK_WEBHOOK_OPS  = _require("SLACK_WEBHOOK_OPS")
SLACK_WEBHOOK_EXEC = _require("SLACK_WEBHOOK_EXEC")
RANA_UID           = os.getenv("RANA_SLACK_UID", "U026W3CCKLG")

FALLBACK_MENTION = "<!subteam^S06URQSJGEN>"  # @us-taxops-leaders (reporter fallback)

MEN_LEADERS = "<!subteam^S06URQSJGEN>"  # @us-taxops-leaders
MEN_LEADS2  = "<!subteam^S0ANS8X2B7Y>"  # @taxops-pillar-leads (WFO 72h)

# US TaxOps Region Coordinators — when no region label / no mapped region lead
REGION_COORDINATORS_MENTION = "<!subteam^S0BAR97SKDG>"

JIRA_PROJECT = "PF"
ISSUE_TYPE   = "Ops - Customer Task"

CH_OPS   = "ops"
CH_LEAD  = "ops"
CH_EXEC  = "exec"
CH_ERROR = "ops"

GOVERNANCE_START = "2026-05-18"

REGION_LEADS = {
    "west-region":      ("U03BFEP9614", "U0789C02H6F"),
    "south-region":     ("U04HQQ0TEDN", "U064GL0HC1X"),
    "northeast-region": ("U08J5762KL1", "U04QRLRCK1D"),
    "midwest-region":   ("U02UTR26FML", "U04EJCJ2X1P"),
    "IRS-region":       ("U05U1E7C8H5", "U05U1E7C8H5"),
    "federal-region":   ("U05U1E7C8H5", "U05U1E7C8H5"),
    "pr-region":        ("U04HQQ0TEDN", "U02UTR26FML"),
}

ET = pytz.timezone("America/New_York")

BASE_JQL = 'project = PF AND issuetype = "Ops - Customer Task"'

# Terminal issues (Done, Closed, etc.) — use in JQL; do not comment or govern closed tickets.
JQL_OPEN_ONLY = "statusCategory != Done"

# TaxOps ownership — A8 applies this label first each poll; downstream scripts scope to it.
TAXOPS_OWNERSHIP_LABEL = "us-taxops-ticket"
JQL_TAXOPS_OWNED     = f'labels = "{TAXOPS_OWNERSHIP_LABEL}"'

COMMON_FIELDS = [
    "summary", "status", "labels", "assignee", "reporter",
    "priority", "created", "updated", "statuscategorychangedate",
]


# -- Slack --------------------------------------------------------------------

def _webhook_url(channel):
    return SLACK_WEBHOOK_EXEC if channel == CH_EXEC else SLACK_WEBHOOK_OPS


def slack_post(text, channel, ticket_key=""):
    """
    POST JSON to the Zapier Catch Hook for this channel (see _webhook_url).

    Threading is implemented in Zapier, not here: when ``ticket_key`` is set
    (Jira issue key, e.g. PF-12345), the Zap should look up a stored Slack
    ``thread_ts`` for that key and reply in thread; otherwise post a new
    parent message and store its ``ts`` under ``ticket_key``. See
    ``taxops/ZAPIER_SLACK_THREADING.md``.
    """
    url     = _webhook_url(channel)
    payload = {"message": text}
    if ticket_key:
        payload["ticket_key"] = ticket_key
    r = requests.post(url, json=payload,
                      headers={"Content-Type": "application/json"}, timeout=30)
    r.raise_for_status()
    return ""


def slack_reply(text, thread_ts, channel, ticket_key=""):
    return slack_post(text, channel, ticket_key=ticket_key)


def post_error(msg):
    """Post error to Slack ops channel. Use GitHub Actions notifications for email alerts."""
    try:
        slack_post(":rotating_light: *TaxOps Error*\n" + msg, CH_ERROR)
    except Exception:
        pass
    print("ERROR: " + msg, file=sys.stderr)


# -- Jira ---------------------------------------------------------------------

def _jira_auth():
    creds = b64encode((JIRA_EMAIL + ":" + JIRA_API_TOKEN).encode()).decode()
    return {
        "Authorization": "Basic " + creds,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def jira_search(jql, fields=None, max_results=100):
    url  = JIRA_BASE_URL + "/rest/api/3/search/jql"
    body = {"jql": jql, "maxResults": max_results}
    if fields:
        body["fields"] = fields
    r = requests.post(url, headers=_jira_auth(), json=body, timeout=30)
    r.raise_for_status()
    data   = r.json()
    issues = data.get("issues", [])
    total  = data.get("total", 0)
    start  = len(issues)
    while start < total and len(issues) < 500:
        body["startAt"] = start
        r = requests.post(url, headers=_jira_auth(), json=body, timeout=30)
        r.raise_for_status()
        batch = r.json().get("issues", [])
        if not batch:
            break
        issues.extend(batch)
        start += len(batch)
    return issues


def get_comments(issue_key):
    url = JIRA_BASE_URL + "/rest/api/3/issue/" + issue_key + "/comment"
    r   = requests.get(url, headers=_jira_auth(),
                       params={"maxResults": 200}, timeout=30)
    r.raise_for_status()
    return r.json().get("comments", [])


def has_auto_flag(issue_key, flag):
    for c in get_comments(issue_key):
        if flag in _adf_to_text(c.get("body", {})):
            return True
    return False


def add_comment(issue_key, text):
    url  = JIRA_BASE_URL + "/rest/api/3/issue/" + issue_key + "/comment"
    body = {
        "body": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph",
                          "content": [{"type": "text", "text": text}]}]
        }
    }
    r = requests.post(url, headers=_jira_auth(), json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def get_labels(issue):
    return issue.get("fields", {}).get("labels", [])


def update_labels(issue_key, labels):
    url = JIRA_BASE_URL + "/rest/api/3/issue/" + issue_key
    r   = requests.put(url, headers=_jira_auth(),
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
    current = get_labels(issue)
    cleaned = [l for l in current if not l.startswith(prefix)]
    if len(cleaned) != len(current):
        update_labels(issue_key, cleaned)


def transition_issue(issue_key, status_name):
    """
    Transition a Jira issue to the named status (case-insensitive match).
    Returns True if successful, False if the transition was not available.
    """
    url = JIRA_BASE_URL + "/rest/api/3/issue/" + issue_key + "/transitions"
    r   = requests.get(url, headers=_jira_auth(), timeout=30)
    r.raise_for_status()
    for t in r.json().get("transitions", []):
        if t.get("to", {}).get("name", "").lower() == status_name.lower():
            r2 = requests.post(url, headers=_jira_auth(),
                               json={"transition": {"id": t["id"]}}, timeout=30)
            r2.raise_for_status()
            return True
    print(f"[transition_issue] '{status_name}' not available for {issue_key}", file=sys.stderr)
    return False


def ops_has_responded(issue_key, reporter_account_id, since_minutes=30):
    """
    Returns True if a non-reporter, non-automation comment was added in the
    last `since_minutes` minutes on a WFO ticket — indicating Ops responded.
    """
    comments = get_comments(issue_key)
    cutoff   = datetime.now(pytz.utc) - timedelta(minutes=since_minutes)
    for c in reversed(comments):
        created = _safe_parse_dt(c.get("created", ""))
        if not created or created < cutoff:
            continue
        # Skip our own AUTO_FLAG comments
        if "AUTO_FLAG:" in _adf_to_text(c.get("body", {})):
            continue
        # Skip comments from the original reporter
        commenter_id = (c.get("author") or {}).get("accountId", "")
        if commenter_id and commenter_id == reporter_account_id:
            continue
        return True
    return False


def restore_governance_labels(issue, issue_key, current_labels, known_labels):
    """
    Check the most recent label changelog entry for stripped governance labels and restore them.
    Only restores labels that exist in known_labels (our governance taxonomy).
    Silent. Returns list of restored label names, or empty list.
    """
    current_set = set(current_labels)
    try:
        url = JIRA_BASE_URL + "/rest/api/3/issue/" + issue_key + "?expand=changelog"
        r   = requests.get(url, headers=_jira_auth(), timeout=30)
        r.raise_for_status()
        histories = r.json().get("changelog", {}).get("histories", [])
    except Exception:
        return []
    for history in sorted(histories, key=lambda h: h.get("created", ""), reverse=True):
        for item in history.get("items", []):
            if item.get("field") == "labels":
                from_str      = (item.get("fromString") or "").strip()
                prev_labels   = set(from_str.split()) if from_str else set()
                removed_known = (prev_labels - current_set) & known_labels
                if removed_known:
                    new_labels = list(current_set | removed_known)
                    update_labels(issue_key, new_labels)
                    issue["fields"]["labels"] = new_labels
                    return list(removed_known)
                return []
    return []


def _adf_to_text(node):
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        if node.get("type") == "mention":
            return node.get("attrs", {}).get("text", "")
        return " ".join(_adf_to_text(c) for c in node.get("content", []))
    if isinstance(node, list):
        return " ".join(_adf_to_text(c) for c in node)
    return ""


def desc_text(issue):
    raw = issue.get("fields", {}).get("description") or {}
    return _adf_to_text(raw)


def region_lead_uid(labels, is_peo=False):
    for lbl, (std, peo) in REGION_LEADS.items():
        if lbl in labels:
            return peo if is_peo else std
    return ""


def reporter_tag_for(issue):
    """Return <@UID> for the ticket reporter, or @us-taxops-leaders fallback."""
    name = (issue.get("fields", {}).get("reporter") or {}).get("displayName", "")
    uid  = slack_uid_for_name(name)
    return f"<@{uid}>" if uid else FALLBACK_MENTION


def lead_tag_for(labels, is_peo=False):
    """Return <@UID> for the region lead, or @us-taxops-region-coordinators if unknown."""
    uid = region_lead_uid(labels, is_peo)
    return f"<@{uid}>" if uid else REGION_COORDINATORS_MENTION


# -- TaxOps team Slack UID lookup (keyed by Jira displayName, lowercase) ------

TAXOPS_SLACK_UIDS = {
    "abhilash jodu":               "U08SSGLP076",
    "aisha fathima":               "U08MEKYFGC8",
    "alekya reddy":                "U0A5RCNL38U",
    "aman modem":                  "U0ARYG5FA1K",
    "anees fathima":               "U08TRSG09FU",
    "ankit gupta":                 "U0ALSHESL1X",
    "ankit tiwari":                "U07LAHU2QKW",
    "anoop asawa":                 "U03BYN69R60",
    "anshu kumar":                 "U08915MRF9B",
    "anthony dcruze":              "U03M0L6K0HZ",
    "anupam baldawa":              "U06TL7D2LG7",
    "anukriti bharadwaj":          "U0B3KJC8WGP",
    "anuradha reddy":              "U031Q7L2BHT",
    "anusha francina":             "U08HDGKBDTR",
    "arnold ashish":               "U031NBG0E82",
    "arvind dubbaka":              "U08G8S8SE07",
    "ashitha rai":                 "U064GL0HC1X",
    "beula nadimidoddi":           "U08R6TD4V8F",
    "bhavitha aila":               "U03P74C19ST",
    "carolina ouellette":          "U0266CFCM0A",
    "christopher trinh":           "U027CLWKKJS",
    "daniel kalyan":               "U056FSEN220",
    "daniel reinoso":              "U027CMM98K0",
    "david ahumada":               "U01HXD21MEC",
    "deepika mothkoj":             "U07CZ72G3BQ",
    "deepthi sree":                "U07P91H077X",
    "emily verdusco":              "U01N8BSCTAB",
    "eurie choi":                  "U031FNR8MD4",
    "gaspar raj":                  "U02V0FHJ6MQ",
    "hanisha manepalli":           "U07PT4H8T3K",
    "hasmukh sharma":              "U02QECD1LD8",
    "jambula naveen":              "U09KRM8EZAA",
    "joshua wilmot":               "U028953EH24",
    "k v santhosh":                "U09AJ5RK50A",
    "lakshmi harika majety":       "U04HQQ0TEDN",
    "lakshmi sridevi iragavarapu": "U092A416KN1",
    "laxmi sirisha":               "U08VCUGSSGG",
    "magdalina augustine":         "U05U1E7C8H5",
    "mahender n":                  "U0B3B3FJ69E",
    "maninder singh":              "U09L6M6EJ1X",
    "manish agarwal":              "U04QRLRCK1D",
    "maria john":                  "U07LLS1QGF3",
    "mohammed naveed":             "U08QQAFAR50",
    "mounika chennaram":           "U08J5762KL1",
    "mounika podishetty":          "U087A5EV82U",
    "mustaqeem ahmed":             "U03MP2PF3SB",
    "nirosha g":                   "U0AKT46FGE4",
    "orlando nieto":               "U03CZS3QMQF",
    "prameela p":                  "U08LUDQ18LC",
    "prajjawal mishra":            "U0B2ENW7DE2",
    "pratima tandle":              "U07HKS3T4BT",
    "prathiksha praveen":          "U0A4R3KC5MJ",
    "priyanka kumari":             "U05UFSXCR0B",
    "priyanka singireddy":         "U0A8L5F490Q",
    "rahul r maniyal":             "U03BFEP9614",
    "rama ponaka":                 "U08RP2NNFV0",
    "ramya yellamali":             "U06D8UC45DW",
    "rana annabi":                 "U026W3CCKLG",
    "rashmita topakulu":           "U07H70FAFJP",
    "rembert mario fernandes":     "U07HKMV7LKT",
    "robin islam":                 "U01F7MRSW5V",
    "roshini arya":                "U08LK62PGVC",
    "ruheen fatima":               "U0789C02H6F",
    "ryan cannedy":                "U026W3ACSU8",
    "sadiya sultana":              "U0903QHPM9U",
    "sai sriram karthik badam":    "U0AJVCAK7QD",
    "sailendra chivukula":         "U03TLFT2Q6A",
    "samba ramya":                 "U07NA2WJLQ2",
    "samarpan pramanik":           "U07PGUKDNLC",
    "sandhya malve":               "U08QEL071P0",
    "sarah garcia":                "U024DAZLD8R",
    "sarika m.b.":                 "U0A7A6ZRS80",
    "shagufta alhamdi":            "U07P93DMEKX",
    "shareef ahmed":               "U09FAGMGAQH",
    "sheetal sharma":              "U06U37MJ59S",
    "shirley zheng":               "U02HU0LG32L",
    "shubhanker modak":            "U08QKUVDZKP",
    "srija valluri":               "U0B21CZS78F",
    "suresh perumal":              "U0AGHQ41681",
    "suresh shinde":               "U08LCCP7U2K",
    "tanmay trivedi":              "U04EJCJ2X1P",
    "tony henriquez":              "U026LRKHS1F",
    "vaishnavi goulikar":          "U02UTR26FML",
    "vanessa abarca":              "U034N8TLGMQ",
    "vemula akash":                "U0AAQTMFH5G",
    "venu ummareddy":              "U0AF7QHFHHP",
    "vijay kumar":                 "U043JD1JSA1",
    "zach russi":                  "U027RKP7VBN",
    "zieshan shaik":               "U086M80JM1R",
}


def slack_uid_for_name(display_name):
    """Look up a TaxOps team member's Slack UID by their Jira display name."""
    return TAXOPS_SLACK_UIDS.get((display_name or "").lower().strip(), "")


# -- Date helpers -------------------------------------------------------------

def _safe_parse_dt(dt_str):
    if not dt_str:
        return None
    s = re.sub(r"\.\d+", "", dt_str)
    s = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", s)
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None


def biz_hours_since(dt_str):
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
        if cur.weekday() < 5:
            day_s = ET.localize(datetime.combine(cur, dtime(9, 0)))
            day_e = ET.localize(datetime.combine(cur, dtime(18, 0)))
            ws    = max(start_et, day_s)
            we    = min(end_et, day_e)
            if we > ws:
                total += (we - ws).total_seconds() / 3600
        cur += timedelta(days=1)
    return total


def biz_days_since(dt_str):
    return biz_hours_since(dt_str) / 9.0


def calendar_hours_since(dt_str):
    start = _safe_parse_dt(dt_str)
    if not start:
        return 0.0
    return (datetime.now(pytz.utc) - start).total_seconds() / 3600


def issue_url(key):
    return JIRA_BASE_URL + "/browse/" + key
