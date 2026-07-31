"""ADR-088 cross-channel identity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class IdentityTest(unittest.TestCase):
    def test_link_resolve_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = base / "data" / "channel_identities.json"
            with patch("gateway.channels.identity.BASE", base), patch(
                "gateway.channels.identity.STORE", store
            ):
                from gateway.channels import identity as ident
                from gateway.channels.routing import clear_route_cache, session_id_for

                clear_route_cache()
                a = ident.link_identity("telegram", "alice", identity_id="id-shared")
                b = ident.link_identity("discord", "alice_d", identity_id="id-shared")
                self.assertEqual(a["identity_id"], "id-shared")
                self.assertEqual(b["identity_id"], "id-shared")
                self.assertEqual(ident.resolve_identity("discord", "alice_d"), "id-shared")
                # Same chat_id + linked identity → same session across channels
                s1 = session_id_for("telegram", "room1", "alice")
                s2 = session_id_for("discord", "room1", "alice_d")
                self.assertEqual(s1, s2)


if __name__ == "__main__":
    unittest.main()
