"""jarvis.desktop_automation.security.recipient_guard — Wrong-recipient and contact disambiguation protection."""

from __future__ import annotations

from typing import List, Optional, Tuple


class RecipientGuard:
    """Enforces strict contact matching to prevent messaging the wrong recipient."""

    @staticmethod
    def disambiguate_contact(query: str, found_contacts: List[str]) -> Tuple[bool, Optional[str], List[str]]:
        """Check for ambiguous contacts.

        Returns: (is_unique, selected_contact, matching_candidates)
        """
        clean_q = query.strip().lower()
        exact_matches = [c for c in found_contacts if c.strip().lower() == clean_q]
        if len(exact_matches) == 1:
            return True, exact_matches[0], exact_matches

        partial_matches = [c for c in found_contacts if clean_q in c.strip().lower()]
        if len(partial_matches) == 1:
            return True, partial_matches[0], partial_matches

        if len(partial_matches) > 1:
            return False, None, partial_matches

        return False, None, []

    @staticmethod
    def assert_active_chat_recipient(active_header_title: str, expected_recipient: str) -> bool:
        """Strictly verify that the open chat header matches the intended recipient."""
        clean_header = active_header_title.strip().lower()
        clean_expected = expected_recipient.strip().lower()
        return clean_expected in clean_header or clean_header in clean_expected
