#!/data/data/com.termux/files/usr/bin/bash
# KerrOS — assign one dependency-wave of issues to the coding agent at a time.
# Regenerated after the backlog audit: false KOS-004 dependency on KOS-005/006
# removed, KOS-012 split into 012a/012b, KOS-014 (port migration cleanup) added,
# KOS-013/KOS-015 (governance decisions) permanently excluded from code waves —
# they're calls for Kerr to make, not tasks for the coding agent to execute.
#
# Usage:
#   ./assign_wave.sh 1          # assign a wave
#   ./assign_wave.sh decisions  # just lists what YOU still need to decide

set -euo pipefail
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
WAVE="${1:?Usage: ./assign_wave.sh <1|2|3|4|5|6|decisions>}"

if [[ "$WAVE" == "decisions" ]]; then
  echo "Governance items — human decisions, never assigned to the coding agent:"
  echo "  KOS-013: LGU/audit-grade scope decision"
  echo "  KOS-015: Resolve orphaned core/ orchestration cluster"
  echo "Resolve these on your own timeline — they don't block any code wave below."
  exit 0
fi

case "$WAVE" in
  1) IDS="KOS-001 KOS-002 KOS-003 KOS-004 KOS-005 KOS-006 KOS-008" ;;   # no dependencies
  2) IDS="KOS-007 KOS-009 KOS-010" ;;                                   # need KOS-004 and/or KOS-008 merged
  3) IDS="KOS-011" ;;                                                    # needs KOS-004 + KOS-008 merged
  4) IDS="KOS-012a" ;;                                                   # needs KOS-011 merged
  5) IDS="KOS-012b" ;;                                                   # needs KOS-012a merged
  6) IDS="KOS-014" ;;                                                    # needs KOS-005, 006, 007 merged — cleanup pass
  *) echo "Unknown wave: $WAVE (valid: 1-6, decisions)"; exit 1 ;;
esac

for id in $IDS; do
  num=$(gh issue list --repo "$REPO" --search "$id in:title" --json number -q '.[0].number')
  if [[ -z "$num" ]]; then
    echo "WARNING: no issue found for $id — skipping"
    continue
  fi
  gh issue edit "$num" --repo "$REPO" --add-assignee copilot-swe-agent \
    && echo "$id (#$num) -> assigned" \
    || echo "$id (#$num) -> FAILED, check coding agent is enabled"
done
