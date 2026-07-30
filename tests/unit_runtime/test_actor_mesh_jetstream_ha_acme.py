"""ADR-029: JetStream cluster failover + ACME cert watch tests."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from runtime.acme_reload import (
    AcmeCertWatcher,
    AcmeConfig,
    acme_paths_to_tls_config,
    certbot_available,
    pem_mtimes_for_acme,
    resolve_acme_paths,
)
from runtime.actor_mesh_tls import ReloadingTlsHolder
from runtime.nats_jetstream import JetStreamError
from runtime.nats_jetstream_cluster import (
    InMemoryClusterJetStream,
    JetStreamClusterClient,
    JetStreamClusterConfig,
)


def _write_self_signed(tmpdir: Path, name: str = "node") -> tuple[Path, Path, Path]:
    key_path = tmpdir / f"{name}-key.pem"
    cert_path = tmpdir / f"{name}-cert.pem"
    try:
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(key_path),
                "-out",
                str(cert_path),
                "-days",
                "1",
                "-nodes",
                "-subj",
                f"/CN={name}",
            ],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise unittest.SkipTest(f"openssl unavailable: {exc}") from exc
    return cert_path, key_path, cert_path  # chain≈cert for lab


class JetStreamClusterTest(unittest.TestCase):
    def test_config_default_off(self):
        cfg = JetStreamClusterConfig.from_mapping({})
        self.assertFalse(cfg.enabled)

    def test_failover_to_secondary(self):
        mem = InMemoryClusterJetStream(servers=["mem://a", "mem://b"])
        client = JetStreamClusterClient(
            cfg=JetStreamClusterConfig(
                enabled=True,
                servers=list(mem.servers),
                stream="kerros",
                failover_retries=2,
            ),
            cluster=mem,
        )
        client.start()
        self.assertEqual(client.stats()["active_url"], "mem://a")
        client.publish("subj", b"one")
        self.assertEqual(mem.stream_len("mem://a"), 1)

        mem.fail_primary()
        client.publish("subj", b"two")
        self.assertEqual(client.stats()["active_url"], "mem://b")
        self.assertGreaterEqual(client.stats()["failovers"], 1)
        self.assertEqual(mem.stream_len("mem://b"), 1)
        client.close()

    def test_all_down_raises(self):
        mem = InMemoryClusterJetStream(servers=["mem://a", "mem://b"])
        mem.fail_primary()
        # Also fail secondary by marking both
        mem._fail.add("mem://b")
        client = JetStreamClusterClient(
            cfg=JetStreamClusterConfig(
                enabled=True, servers=list(mem.servers), failover_retries=1
            ),
            cluster=mem,
        )
        with self.assertRaises(JetStreamError):
            client.start()


class AcmeWatchTest(unittest.TestCase):
    def test_resolve_paths(self):
        cfg = AcmeConfig(enabled=True, live_dir="/tmp/live/example.com")
        paths = resolve_acme_paths(cfg)
        self.assertTrue(str(paths["fullchain"]).endswith("fullchain.pem"))

    def test_watch_reloads_on_mtime(self):
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live" / "example.com"
            live.mkdir(parents=True)
            cert, key, chain = _write_self_signed(live, "ex")
            # ACME layout names
            fullchain = live / "fullchain.pem"
            privkey = live / "privkey.pem"
            chain_pem = live / "chain.pem"
            fullchain.write_bytes(cert.read_bytes())
            privkey.write_bytes(key.read_bytes())
            chain_pem.write_bytes(chain.read_bytes())

            acme = AcmeConfig(
                enabled=True,
                live_dir=str(live),
                domain="example.com",
                watch_interval_s=0,
            )
            tls_cfg = acme_paths_to_tls_config(acme)
            holder = ReloadingTlsHolder.from_config(tls_cfg)
            watcher = AcmeCertWatcher(cfg=acme, tls_holder=holder)
            self.assertFalse(watcher.check_once())  # first sync
            self.assertEqual(watcher.stats()["reloads"], 0)

            time.sleep(0.05)
            os.utime(fullchain, (time.time() + 2, time.time() + 2))
            self.assertTrue(watcher.check_once())
            self.assertEqual(watcher.stats()["reloads"], 1)
            self.assertTrue(pem_mtimes_for_acme(acme)["fullchain"] > 0)

    def test_certbot_probe_skipped_by_default(self):
        watcher = AcmeCertWatcher(cfg=AcmeConfig(enabled=True))
        out = watcher.maybe_probe_certbot()
        self.assertTrue(out.get("skipped"))
        # Soft availability check does not raise.
        self.assertIsInstance(certbot_available(), bool)


if __name__ == "__main__":
    unittest.main()
