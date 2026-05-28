"""
A7 - New Scope Detector
Polling every 15 min.

Scans comments added in the last 30 minutes for language indicating
new scope has been added to an existing ticket.

Detection signals (regex):
  - References to a different company/entity/client
  - New PCIH/FFID/EIN not in original description
  - Phrases: "also need to", "separate issue", "another company",
    "different client", "additionally", "also fix", "unrelated"

Dedup: AUTO_FLAG:NEW_SCOPE:<comment_id> per comment.
Label: new-scope-detected
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from common import _safe_parse_dt   # private helper not exported by import *
from datetime import datetime, timedelta
import pytz

SCOPE_PATTERNS = [
    r"also\s+need\s+to",
    r"separate\s+issue",
    r"another\s+company",
    r"different\s+client",
    r"different\s+entity",
    r"different\s+company",
    r"unrelated\s+(issue|ticket|matter)",
    r"also\s+fix",
    r"also\s+update",
    r"while\s+(you'?re|we'?re)\s+at\s+it",
    r"additionally\b",
    r"new\s+company",
    r"new\s+client",
    r"new\s+entity",
    r"new\s+(EIN|PCIH|FFID)\s*[:\-]?\s*\d",
    r"different\s+(state|tax\s+type)",
]
SCOPE_RE = re.compile("|".join(SCOPE_PATTERNS), re.IGNORECASE)


def _is_recent(comment, cutoff_dt):
    created = _safe_parse_dt(comment.get("created", ""))
    return created and created >= cutoff_dt


def run():
    cutoff = datetime.now(pytz.utc) - timedelta(minutes=30)

    issues = jira_search(
        f'{BASE_JQL} AND status != Done AND updated >= "-30m"',
        fields=COMMON_FIELDS + ["description"],
    )
    print(f"[A7] {len(issues)} recently updated tickets to scan")

    for issue in issues:
        key     = issue["key"]
        fields  = issue["fields"]
        summary = fields.get("summary", "(no summary)")
        url     = issue_url(key)
        labels  = get_labels(issue)
        is_peo  = "e2e-peo" in labels
        reporter_name = (fields.get("reporter") or {}).get("displayName", "Reporter")
        reporter_uid  = slack_uid_for_name(reporter_name)
        reporter_tag  = f"<@{reporter_uid}>" if reporter_uid else reporter_name

        try:
            comments = get_comments(key)
            for comment in comments:
                if not _is_recent(comment, cutoff):
                    continue

                comment_id   = comment.get("id", "")
                comment_text = _adf_to_text(comment.get("body", {}))

                if not SCOPE_RE.search(comment_text):
                    continue

                flag = f"AUTO_FLAG:NEW_SCOPE:{comment_id}"
                if has_auto_flag(key, flag):
                    continue

                lead_uid = region_lead_uid(labels, is_peo)
                lead_tag = f"<@{lead_uid}>" if lead_uid else ""

                add_comment(key,
                    f"{flag} -- Potential new scope detected in comment {comment_id}.\n\n"
                    f"Flagged language: \"{comment_text[:200]}\"\n\n"
                    f"If this is new scope, please open a separate Jira ticket and link it here."
                )
                add_label(issue, key, "new-scope-detected")

                author = (comment.get("author") or {}).get("displayName", "Unknown")
                slack_post(
                    f":mag: *New Scope Detected* {lead_tag} {reporter_tag} — <{url}|{key}>\n"
                    f"{summary}\n"
                    f"Comment by {author}: \"{comment_text[:150]}\"\n"
                    f"Please open a separate ticket if this is new scope.",
                    CH_OPS,
                    ticket_key=key,
                )

        except Exception as e:
            post_error(f"A7 error on {key}: {e}")


if __name__ == "__main__":
    run()
