import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2]


class InstallNginxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        (self.root / "deploy" / "scripts").mkdir(parents=True)
        shutil.copy2(SOURCE_ROOT / "deploy/scripts/install-nginx.sh",
                     self.root / "deploy/scripts/install-nginx.sh")
        shutil.copytree(SOURCE_ROOT / "deploy/nginx", self.root / "deploy/nginx")
        self.etc = Path(self.tmp.name) / "etc-nginx"
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        self.log = Path(self.tmp.name) / "commands.log"
        self._fake_command("nginx", '''echo "nginx $*" >> "$COMMAND_LOG"
exit "$NGINX_EXIT"''')
        self._fake_command("systemctl", '''echo "systemctl $*" >> "$COMMAND_LOG"
exit "$SYSTEMCTL_EXIT"''')

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_command(self, name, body):
        path = self.bin / name
        path.write_text("#!/usr/bin/env bash" + chr(10) + body + chr(10))
        path.chmod(0o755)

    def _run(self, **extra):
        env = os.environ.copy()
        env.update({
            "PATH": str(self.bin) + os.pathsep + env["PATH"],
            "COMMAND_LOG": str(self.log),
            "NGINX_ETC_DIR": str(self.etc),
            "NGINX_BIN": "nginx",
            "SYSTEMCTL_BIN": "systemctl",
            "NGINX_EXIT": "0",
            "SYSTEMCTL_EXIT": "0",
        })
        env.update({k: str(v) for k, v in extra.items()})
        return subprocess.run(
            ["bash", str(self.root / "deploy/scripts/install-nginx.sh")],
            text=True, capture_output=True, env=env, check=False,
        )

    def test_installs_site_and_reloads_only_after_validation(self):
        default_site = self.etc / "sites-enabled/default"
        default_site.parent.mkdir(parents=True)
        default_site.write_text("unrelated")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.etc / "sites-available/netcore").is_file())
        self.assertEqual(
            (self.etc / "sites-enabled/netcore").readlink(),
            self.etc / "sites-available/netcore",
        )
        self.assertTrue(default_site.exists())
        self.assertTrue((self.etc / "conf.d/netcore-limits.conf").is_file())
        self.assertEqual(self.log.read_text().splitlines(),
                         ["nginx -t", "systemctl reload nginx"])

    def test_refuses_to_overwrite_conflicting_site(self):
        available = self.etc / "sites-available"
        available.mkdir(parents=True)
        target = available / "netcore"
        target.write_text("operator configuration")
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "operator configuration")
        self.assertFalse(self.log.exists())

    def test_validation_failure_rolls_back_created_files_and_link(self):
        result = self._run(NGINX_EXIT=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.etc / "sites-available/netcore").exists())
        self.assertFalse((self.etc / "sites-enabled/netcore").exists())
        self.assertFalse((self.etc / "conf.d/netcore-limits.conf").exists())
        self.assertEqual(self.log.read_text().splitlines(), ["nginx -t"])

    def test_reload_failure_rolls_back_created_files_and_link(self):
        result = self._run(SYSTEMCTL_EXIT=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.etc / "sites-available/netcore").exists())
        self.assertFalse((self.etc / "sites-enabled/netcore").exists())
        self.assertEqual(self.log.read_text().splitlines(),
                         ["nginx -t", "systemctl reload nginx"])

    def test_refuses_non_symlink_activation_conflict(self):
        enabled = self.etc / "sites-enabled"
        enabled.mkdir(parents=True)
        target = enabled / "netcore"
        target.write_text("operator file")
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "operator file")
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
