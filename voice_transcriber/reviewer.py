"""CLI for reviewing and approving auto-generated glossary candidates.

Run via the daemon socket command ``review`` or directly:

    python -m voice_transcriber.reviewer

Interactive prompts let you approve or reject each pending term.
Approved terms are appended to the domain glossary JSON on disk.
"""

from __future__ import annotations

import sys

from voice_transcriber import history as history_module


def _review_pending(min_occurrences: int = 1) -> None:
    """Interactive review loop."""
    pending = history_module.list_pending_terms(
        status="pending",
        min_occurrences=min_occurrences,
    )

    if not pending:
        print("No pending glossary terms to review.")
        return

    print(f"\n{len(pending)} pending glossary term(s) (min occurrences: {min_occurrences}):\n")

    approved = 0
    rejected = 0
    skipped = 0

    for row in pending:
        print(f"  Domain:   {row['domain']}")
        print(f"  Alias:    '{row['alias']}'")
        print(f"  Maps to:  '{row['canonical']}'")
        print(f"  Seen:     {row['occurrence_count']} time(s)")
        print(f"  Context:  '{row['raw'][:60]}...' \u2192 '{row['corrected'][:60]}...'")
        print()

        answer = input("[a]pprove / [r]eject / [s]kip / [q]uit? ").strip().lower()

        if answer.startswith("a"):
            history_module.approve_pending_term(row["id"])
            print(f"    ✓ Approved: '{row['alias']}' \u2192 '{row['canonical']}'\n")
            approved += 1
        elif answer.startswith("r"):
            history_module.reject_pending_term(row["id"])
            print(f"    ✗ Rejected: '{row['alias']}'\n")
            rejected += 1
        elif answer.startswith("q"):
            print("Quit review session.")
            break
        else:
            print("    → Skipped\n")
            skipped += 1

    print(f"Review complete: {approved} approved, {rejected} rejected, {skipped} skipped.")


def main(argv: list[str] | None = None) -> int:
    """Entry point for the reviewer CLI."""
    argv = argv or sys.argv[1:]

    min_occurrences = 1
    if argv and argv[0].isdigit():
        min_occurrences = int(argv[0])

    _review_pending(min_occurrences=min_occurrences)
    return 0


if __name__ == "__main__":
    sys.exit(main())
