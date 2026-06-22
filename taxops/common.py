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

GOVERNANCE_START = "2026-05-18"  # cleanup_governance_labels.py only; not used in polling JQL

# Appfire Connector for Salesforce & Jira — issue entity property (readable via Jira REST API)
SF_ASSOCIATIONS_PROPERTY = "com.servicerocket.jira.cloud.issue.salesforce.associations"
SF_CASE_DESC_PATTERN     = re.compile(r"(salesforce\.com|Case\s*#\s*\d+|SF-\d+)", re.IGNORECASE)
MISSING_SFDC_LINK_LABEL  = "missing-sfdc-link"

REGION_LEADS = {
    "west-region":      ("U03BFEP9614", "U0789C02H6F"),
    "south-region":     ("U04HQQ0TEDN", "U064GL0HC1X"),
    "northeast-region": ("U08J5762KL1", "U04QRLRCK1D"),
    "midwest-region":   ("U02UTR26FML", "U04EJCJ2X1P"),
    "IRS-region":       ("U05U1E7C8H5", "U05U1E7C8H5"),
    "federal-region":   ("U05U1E7C8H5", "U05U1E7C8H5"),
    "pr-region":        ("U04HQQ0TEDN", "U02UTR26FML"),
}

STANDARD_REGION_LABELS = set(REGION_LEADS.keys())
FILINGS_AMENDMENTS_REGION = "filings-amendments-region"

AMENDMENT_WORKSTREAM = "Amendment_task"
FILING_WORKSTREAM    = "filing_task"
TEAM_AMENDMENTS      = "us-amendments"
TEAM_FILINGS         = "us-filings"
TEAM_TAX_FILINGS     = "us-tax-filings"  # legacy alias for filing workstream

WORKSTREAM_TEAM_LEADS = {
    (AMENDMENT_WORKSTREAM, TEAM_AMENDMENTS): "U03MP2PF3SB",  # Mustaqueem Ahmed
    (FILING_WORKSTREAM, TEAM_FILINGS):       "U02HU0LG32L",  # Shirley Zheng
    (FILING_WORKSTREAM, TEAM_TAX_FILINGS):   "U02HU0LG32L",
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


def get_issue_property(issue_key, property_key):
    """Return entity property value, or None if unset (404)."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/properties/{property_key}"
    r   = requests.get(url, headers=_jira_auth(), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("value")


def get_remote_issue_links(issue_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/remotelink"
    r   = requests.get(url, headers=_jira_auth(), timeout=30)
    r.raise_for_status()
    return r.json()


def _salesforce_property_has_case(prop_value):
    """True when Appfire connector entity property includes a Salesforce Case."""
    if not prop_value or not isinstance(prop_value, dict):
        return False

    types = str(prop_value.get("types") or "")
    if re.search(r"\bCase\b", types, re.IGNORECASE):
        return True

    associations = prop_value.get("associations") or {}
    if isinstance(associations, dict):
        for entry in associations.values():
            if isinstance(entry, dict) and str(entry.get("son", "")).lower() == "case":
                return True
    return False


def description_has_salesforce_reference(text):
    return bool(SF_CASE_DESC_PATTERN.search(text or ""))


def has_salesforce_case_linked(issue_key):
    """
    True when Connector for Salesforce has a Case associated, or a Salesforce
    remote link is present on the issue.
    """
    try:
        prop = get_issue_property(issue_key, SF_ASSOCIATIONS_PROPERTY)
        if _salesforce_property_has_case(prop):
            return True
    except Exception as e:
        print(f"[SFDC] Could not read associations for {issue_key}: {e}", file=sys.stderr)

    try:
        for link in get_remote_issue_links(issue_key):
            obj   = link.get("object") or {}
            url   = (obj.get("url") or "").lower()
            title = (obj.get("title") or "").lower()
            if "salesforce.com" in url or "/case/" in url:
                return True
            if "salesforce" in url and "case" in title:
                return True
    except Exception as e:
        print(f"[SFDC] Could not read remote links for {issue_key}: {e}", file=sys.stderr)

    return False


def has_auto_flag(issue_key, flag):
    for c in get_comments(issue_key):
        if flag in _adf_to_text(c.get("body", {})):
            return True
    return False


def hours_since_comment_matching(issue_key, text_substring):
    """Hours since the latest comment containing substring, or None if never."""
    latest = None
    for c in get_comments(issue_key):
        text = _adf_to_text(c.get("body", {}))
        if text_substring not in text:
            continue
        dt = _safe_parse_dt(c.get("created", ""))
        if dt and (latest is None or dt > latest):
            latest = dt
    if latest is None:
        return None
    return (datetime.now(pytz.utc) - latest).total_seconds() / 3600


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


def ops_has_responded(issue_key, reporter_account_id, since_dt=None, assignee_account_id=None):
    """
    True when the TaxOps reporter (or current assignee) commented since `since_dt`,
    indicating Ops responded to Engineering's WFO request.
    """
    if since_dt is None:
        return False

    ops_ids = {aid for aid in (reporter_account_id, assignee_account_id) if aid}
    if not ops_ids:
        return False

    for c in get_comments(issue_key):
        created = _safe_parse_dt(c.get("created", ""))
        if not created or created < since_dt:
            continue
        if "AUTO_FLAG:" in _adf_to_text(c.get("body", {})):
            continue
        commenter_id = (c.get("author") or {}).get("accountId", "")
        if commenter_id in ops_ids:
            return True
    return False


def status_entered_at(issue_key, status_name):
    """UTC datetime when the issue last transitioned to status_name, or None."""
    try:
        url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}?expand=changelog"
        r   = requests.get(url, headers=_jira_auth(), timeout=30)
        r.raise_for_status()
        histories = r.json().get("changelog", {}).get("histories", [])
    except Exception as e:
        print(f"[WFO] Could not read changelog for {issue_key}: {e}", file=sys.stderr)
        return None

    target = status_name.lower()
    latest = None
    for history in histories:
        for item in history.get("items", []):
            if item.get("field") != "status":
                continue
            if (item.get("toString") or "").lower() != target:
                continue
            dt = _safe_parse_dt(history.get("created", ""))
            if dt and (latest is None or dt > latest):
                latest = dt
    return latest


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
    uid = workstream_team_lead_uid(labels)
    if uid:
        return uid
    for lbl, (std, peo) in REGION_LEADS.items():
        if lbl in labels:
            return peo if is_peo else std
    return ""


def workstream_team_lead_uid(labels):
    """Region lead override for filings/amendments workstream + team combos."""
    label_set = set(labels)
    for (workstream, team), uid in WORKSTREAM_TEAM_LEADS.items():
        if workstream in label_set and team in label_set:
            return uid
    return ""


def is_filings_amendments_routed(labels):
    """Tickets routed via Amendment_task or filing_task + matching team label."""
    label_set = set(labels)
    if AMENDMENT_WORKSTREAM in label_set and TEAM_AMENDMENTS in label_set:
        return True
    if FILING_WORKSTREAM in label_set and (TEAM_FILINGS in label_set or TEAM_TAX_FILINGS in label_set):
        return True
    return False


def has_geographic_label(labels):
    label_set = set(labels)
    if label_set & STANDARD_REGION_LABELS:
        return True
    return FILINGS_AMENDMENTS_REGION in label_set


def normalize_filings_amendments_region(issue, issue_key, labels):
    """
    For amendment/filing routed tickets, ensure filings-amendments-region is set.
    If a standard geographic region label is present instead, replace it silently.
    Returns (labels, changed).
    """
    if not is_filings_amendments_routed(labels):
        return labels, False

    label_set = set(labels)
    std_present = label_set & STANDARD_REGION_LABELS

    if FILINGS_AMENDMENTS_REGION in label_set:
        if not std_present:
            return labels, False
        new_labels = [l for l in labels if l not in std_present]
        update_labels(issue_key, new_labels)
        issue["fields"]["labels"] = new_labels
        return new_labels, True

    if std_present:
        new_labels = [l for l in labels if l not in std_present]
        new_labels.append(FILINGS_AMENDMENTS_REGION)
        update_labels(issue_key, new_labels)
        issue["fields"]["labels"] = new_labels
        return new_labels, True

    return labels, False


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
