"""Keyrings that hardware setup installs into the target (t2-arch-packages on
T2 Macs) are trusted once the per-machine keyring is complete."""

import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "configs/airootfs/usr/share/omarchy-iso"))
sys.modules.setdefault(
    "orchestrator.archinstall_adapter",
    types.ModuleType("orchestrator.archinstall_adapter"),
)
from orchestrator import phases_impl  # noqa: E402


class HardwareKeyringsTest(unittest.TestCase):
    def _ctx(self, target: Path, proc=None):
        state = {} if proc is None else {"target_keyring_proc": proc}
        return types.SimpleNamespace(target=target, state=state)

    def test_populates_a_present_hardware_keyring(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            keyrings = target / "usr/share/pacman/keyrings"
            keyrings.mkdir(parents=True)
            (keyrings / "t2-arch-packages.gpg").write_bytes(b"key")
            with mock.patch.object(phases_impl.subprocess, "run") as run, \
                    mock.patch.object(phases_impl, "info"):
                phases_impl._populate_hardware_keyrings(self._ctx(target))
            # reset-failed, then the populate as a transient unit, so systemd
            # ends the gpg-agent pacman-key leaves behind in the target.
            self.assertEqual(run.call_count, 2)
            argv = run.call_args.args[0]
            self.assertEqual(argv[:5], ["systemd-run", "--wait", "--pipe", "--collect", "--quiet"])
            self.assertEqual(argv[5], f"--unit={phases_impl.HARDWARE_KEYRING_UNIT}")
            self.assertEqual(argv[6:8], ["sh", "-c"])
            script = argv[8]
            self.assertIn(f"pacman-key --gpgdir {target / 'etc/pacman.d/gnupg'}", script)
            self.assertIn(f"--populate-from {keyrings}", script)
            self.assertTrue(script.endswith("--populate t2-arch-packages"))
            self.assertTrue(run.call_args.kwargs["check"])

    def test_skips_when_no_hardware_keyring_is_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(phases_impl.subprocess, "run") as run:
                phases_impl._populate_hardware_keyrings(self._ctx(Path(tmp)))
            run.assert_not_called()

    def test_join_populates_only_after_a_successful_keyring_init(self):
        for returncode, expected_calls in ((0, 1), (1, 0)):
            with self.subTest(returncode=returncode):
                proc = mock.Mock(returncode=returncode)
                proc.communicate.return_value = ("", None)
                with mock.patch.object(phases_impl, "_populate_hardware_keyrings") as populate:
                    phases_impl._join_target_keyring_init(
                        self._ctx(Path("/nonexistent"), proc), raise_on_error=False
                    )
                self.assertEqual(populate.call_count, expected_calls)


if __name__ == "__main__":
    unittest.main()
