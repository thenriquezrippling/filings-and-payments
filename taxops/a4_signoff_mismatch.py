"""
A4 — Region Lead Sign-Off Mismatch Detector
Polling every 15 min.

Checks description for "Reviewed and signed off by: [Name]".
Flags tickets where:
  - Sign-off line is entirely absent
  - Sign-off name is blank / placeholder

Expected lead per region is looked up from REGION_LEADS in common.py.
Full name-match validation requires knowing display names; this script
flags absence and can be extended with a LEAD_NAMES env var map.

Dedup: AUTO_FLAG:SIGNOFF_MISMATCH
Label:  signoff-mismatch (added/removed)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

SIGNOFF_RE   = re.compile(r"reviewed and signed off by\s*:\s*(.+)", re.IGNORECASE)
REGION_LABELS_ALL = {
    "west-region", "south-region", "northeast-region",
    "midwest-region", "IRS-region", "federal-region", "pr-region",
}
# For IRS/federal/pr-region sign-off presence is checked only (no name match)
SIGNOFF_PRESENCE_ONLY = {"IRS-region", "federal-region", "pr-region"}


def _check_signoff(issue):
    """
    Return (ok: bool, reason: str).
    ok=True means sign-off is acceptable.
    """
    text   = desc_text(issue)
    labels = set(get_labels(issue))
    match  = SIGNOFF_RE.search(text)

    if not match:
        # No sign-off line at all
        return False, '"Reviewed and signed off by:" line is missing from description'

    name = match.group(1).strip()
    if not name or name.lower() in ("", "name", "tbd", "n/a", "-"):
        return False, f'Sign-off line present but name is empty or placeholder: "{name}"'

    # For regions that require name match (non-IRS/federal/pr),
    # we verify the sign-off exists for the correct region.
    # Full name validation would require a Slack display-name lookup;
    # set LEAD_NAMES_JSON env var as {"U03BFEP9614": "Jane Smith", ...} to enable.
    lead_names_raw = os.environ.get("LEAD_NAMES_JSON", "{}")
    try:
        import json
        lead_names = json.loads(lead_names_raw)  # {uid: display_name}
    except Exception:
        lead_names = {}

    region_present = labels & REGION_LABELS_ALL
    if region_present and lead_names:
        is_peo   = "e2e-peo" in labels
        lead_uid = region_lead_uid(list(labels), is_peo)
        expected_name = lead_names.get(lead_uid, "")
        if expected_name and expected_name.lower() not in name.lower():
            return False, (
                f'Sign-off says "{name}" but expected "{expected_name}" '
                f'for region {next(iter(region_present))}'
            )

    return True, ""


def run():
    issues = jira_search(
        f'{BASE_JQL} AND status != Done AND updated >= "-30m"',
        fields=COMMON_FIELDS + ["description"],
    )
    print(f"[A4] {len(issues)} recently updated tickets to check")

    for issue in issues:
        key     = issue["key"]
        fields  = issue["fields"]
        summary = fields.get("summary", "(no summary)")
        url     = issue_url(key)
        labels  = get_labels(issue)

        try:
            ok, reason = _check_signoff(issue)

            if not ok:
                if not has_auto_flag(key, "AUTO_FLAG:SIGNOFF_MISMATCH"):
                    comment_text = (
                        f"AUTO_FLAG:SIGNOFF_MISMATCH — Sign-Off Validation Failed.\n\n"
                        f"Reason: {reason}\n\n"
                        f'Please update the description with the correct '
                        f'"Reviewed and signed off by: [Lead Name]" line.'
                    )
                    add_comment(key, comment_text)
                    add_label(issue, key, "signoff-mismatch")

                    is_peo   = "e2e-peo" in labels
                    lead_uid = region_lead_uid(labels, is_peo)
                    lead_tag = f"<@{lead_uid}> " if lead_uid else ""

                    slack_post(
                        f":pencil2: *Sign-Off Mismatch* {lead_tag}— <{url}|{key}>\n"
                        f"{summary}\n{reason}",
                        CH_LEAD,
                    )
            else:
                if "signoff-mismatch" in labels:
                    remove_label(issue, key, "signoff-mismatch")
                    print(f"[A4] {key} sign-off now valid — removed signoff-mismatch")

        except Exception as e:
            post_error(f"A4 error on {key}: {e}")


if __name__ == "__main__":
    run()
