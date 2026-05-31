"""
A4 — Region Lead Sign-Off Mismatch Detector
Polling every 15 min (Mon–Fri).

Checks description for "Reviewed and signed off by: [Name]".
Flags tickets where sign-off line is absent or name is blank/placeholder.

Exempt reporters (no sign-off required): Vijay Kumar, Rashmita Topakulu
Dedup: AUTO_FLAG:SIGNOFF_MISMATCH
Label: signoff-mismatch (added/removed)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

SIGNOFF_RE = re.compile(r"reviewed and signed off by\s*:\s*(.+)", re.IGNORECASE)
EXEMPT_REPORTER_NAMES = {"vijay kumar", "rashmita topakulu"}


def _check_signoff(issue):
    text  = desc_text(issue)
    match = SIGNOFF_RE.search(text)

    if not match:
        return False, '"Reviewed and signed off by:" line is missing from the description'

    name = match.group(1).strip()
    if not name or name.lower() in ("", "name", "tbd", "n/a", "-"):
        return False, f'Sign-off line is present but the name is empty or a placeholder: "{name}"'

    return True, ""


def run():
    issues = jira_search(
        f'{BASE_JQL} AND status != Done AND created >= "{GOVERNANCE_START}" AND updated >= "-30m"',
        fields=COMMON_FIELDS + ["description"],
    )
    print(f"[A4] {len(issues)} recently updated tickets to check")

    for issue in issues:
        key     = issue["key"]
        fields  = issue["fields"]
        summary = fields.get("summary", "(no summary)")
        url     = issue_url(key)
        labels  = get_labels(issue)

        reporter_name = ((fields.get("reporter") or {}).get("displayName") or "").lower()
        if reporter_name in EXEMPT_REPORTER_NAMES:
            if "signoff-mismatch" in labels:
                remove_label(issue, key, "signoff-mismatch")
            continue

        try:
            ok, reason = _check_signoff(issue)

            if not ok:
                if not has_auto_flag(key, "AUTO_FLAG:SIGNOFF_MISMATCH"):
                    add_comment(key,
                        f"AUTO_FLAG:SIGNOFF_MISMATCH — Sign-Off Validation Failed.\n\n"
                        f"Reason: {reason}\n\n"
                        f'Please update the description with the correct '
                        f'"Reviewed and signed off by: [Lead Name]" line.'
                    )
                    add_label(issue, key, "signoff-mismatch")

                    is_peo   = "e2e-peo" in labels
                    rep_tag  = reporter_tag_for(issue)
                    lead_tag = lead_tag_for(labels, is_peo)

                    slack_post(
                        f":pencil2: *Sign-Off Mismatch* {rep_tag} {lead_tag} — <{url}|{key}>\n"
                        f"{summary}\n"
                        f"*Reason:* {reason}",
                        CH_LEAD,
                        ticket_key=key,
                    )
            else:
                if "signoff-mismatch" in labels:
                    remove_label(issue, key, "signoff-mismatch")
                    print(f"[A4] {key} sign-off now valid — removed signoff-mismatch")

        except Exception as e:
            post_error(f"A4 error on {key}: {e}")


if __name__ == "__main__":
    run()
