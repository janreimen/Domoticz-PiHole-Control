"""deploy.sh in local mode, into a temporary plugins directory (no Domoticz, no restart)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "deploy.sh")
sys.path.insert(0, ROOT)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def run(cmd, **kw):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                          timeout=60, **kw)


@unittest.skipUnless(shutil.which("bash") and shutil.which("tar") and os.name == "posix", "needs bash and tar")
class DeployScriptTests(unittest.TestCase):
    script = SCRIPT

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="piholectl-deploy-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.plugins = os.path.join(self.tmp, "plugins")
        os.makedirs(self.plugins)
        self.dir = os.path.join(self.plugins, "Domoticz-PiHole-Control")
        self.backups = os.path.join(self.tmp, "backups")

    def deploy(self, *args, expect=0):
        cmd = ["bash", self.script, "--dir", self.dir, "--backup-dir", self.backups, "--no-restart"] + list(args)
        proc = run(cmd, cwd=self.tmp)
        self.assertEqual(proc.returncode, expect, proc.stdout)
        return proc.stdout

    def backup_files(self):
        return sorted(os.listdir(self.backups)) if os.path.isdir(self.backups) else []

    def test_dry_run_changes_nothing(self):
        out = self.deploy("--dry-run")
        self.assertIn("plugin.py", out)
        self.assertIn("pihole_control/api.py", out)
        self.assertEqual(os.listdir(self.plugins), [])
        self.assertEqual(self.backup_files(), [])

    def test_dry_run_on_an_existing_install_changes_nothing_either(self):
        self.deploy()
        marker = os.path.join(self.dir, "plugin.py")
        with open(marker, "a") as fh:
            fh.write("\n# local edit\n")
        out = self.deploy("--dry-run")
        self.assertIn("[dry-run]", out)
        self.assertIn("# local edit", read(marker))
        self.assertEqual(self.backup_files(), [])

    def test_fresh_install_copies_only_runtime_files(self):
        out = self.deploy()
        self.assertIn("new install", out)
        self.assertIn("the new files parse", out)
        for path in ("plugin.py", "pihole_control/__init__.py", "pihole_control/devices.py", "README.md", "LICENSE",
                     "docs/DEVICES.md"):
            self.assertTrue(os.path.exists(os.path.join(self.dir, path)), path)
        for path in ("tests", "dist", ".git", "deploy.sh", "Makefile", "tools"):
            self.assertFalse(os.path.exists(os.path.join(self.dir, path)), path)
        for _, dirs, _ in os.walk(self.dir):
            self.assertNotIn("__pycache__", dirs)
        self.assertEqual(self.backup_files(), [])

    def test_update_backs_up_outside_the_plugin_directory_and_keeps_foreign_files(self):
        self.deploy()
        with open(os.path.join(self.dir, "local-notes.txt"), "w") as fh:
            fh.write("mine")
        self.deploy()
        self.assertEqual(len(self.backup_files()), 1)
        self.assertEqual(os.listdir(self.plugins), ["Domoticz-PiHole-Control"])    # nothing else is loaded as a plugin
        self.assertTrue(os.path.exists(os.path.join(self.dir, "local-notes.txt")))

    def test_update_removes_files_the_new_version_no_longer_has(self):
        self.deploy()
        stale = os.path.join(self.dir, "pihole_control", "old_module.py")
        with open(stale, "w") as fh:
            fh.write("x = 1\n")
        self.deploy()
        self.assertFalse(os.path.exists(stale))

    def test_only_the_newest_backups_are_kept(self):
        self.deploy()
        for _ in range(4):
            self.deploy("--keep", "2")
        self.assertEqual(len(self.backup_files()), 2)

    def test_two_deployments_in_the_same_second_do_not_overwrite_each_other_s_backup(self):
        self.deploy()
        self.deploy("--keep", "10")
        self.deploy("--keep", "10")
        self.assertEqual(len(set(self.backup_files())), 2)

    def test_rollback_restores_the_previous_copy(self):
        self.deploy()
        marker = os.path.join(self.dir, "plugin.py")
        with open(marker, "a") as fh:
            fh.write("\n# local edit\n")
        self.deploy()                                                  # replaces the edited copy, backs it up
        self.assertNotIn("# local edit", read(marker))
        self.deploy("--rollback")
        self.assertIn("# local edit", read(marker))

    def test_rollback_without_backup_fails_cleanly(self):
        self.deploy()
        out = self.deploy("--rollback", expect=1)
        self.assertIn("no backup found", out)

    def test_unusable_backup_directory_aborts_before_touching_the_install(self):
        self.deploy()
        marker = os.path.join(self.dir, "plugin.py")
        with open(marker, "a") as fh:
            fh.write("\n# keep me\n")
        blocker = os.path.join(self.tmp, "blocker")
        open(blocker, "w").close()
        self.backups = os.path.join(blocker, "sub")                     # cannot be created: parent is a file
        out = self.deploy(expect=1)
        self.assertIn("nothing was changed", out)
        self.assertIn("# keep me", read(marker))

    def test_a_copy_that_does_not_parse_never_replaces_the_working_install(self):
        self.deploy()
        marker = os.path.join(self.dir, "pihole_control", "api.py")
        before = read(marker)
        broken = os.path.join(self.tmp, "broken-source")
        shutil.copytree(ROOT, broken, ignore=shutil.ignore_patterns(".git", "__pycache__", "dist"))
        with open(os.path.join(broken, "pihole_control", "api.py"), "a") as fh:
            fh.write("\ndef broken(:\n")
        proc = run(["bash", os.path.join(broken, "deploy.sh"), "--dir", self.dir, "--backup-dir", self.backups,
                    "--no-restart"], cwd=self.tmp)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("do not parse", proc.stdout)
        self.assertEqual(read(marker), before)
        self.assertEqual(self.backup_files(), [])
        left_over = [name for name in os.listdir(tempfile.gettempdir()) if name.startswith("piholectl.")]
        self.assertEqual([n for n in left_over if os.path.getmtime(os.path.join(tempfile.gettempdir(), n))
                          > os.path.getmtime(self.tmp)], [], "the staging directory was not removed")

    def test_restart_command_is_run_and_a_failing_one_does_not_fail_the_deployment(self):
        marker = os.path.join(self.tmp, "restarted")
        cmd = ["bash", self.script, "--dir", self.dir, "--backup-dir", self.backups, "--restart-cmd", "touch " + marker]
        proc = run(cmd)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertTrue(os.path.exists(marker))
        cmd[-1] = "exit 3"
        proc = run(cmd)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("restart command failed", proc.stdout)

    def test_no_restart_is_said_out_loud(self):
        self.assertIn("NOT restarted", self.deploy())

    def test_bad_arguments(self):
        proc = run(["bash", self.script, "--nope"])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unknown option", proc.stdout)
        self.assertEqual(run(["bash", self.script, "--keep", "0"]).returncode, 1)
        self.assertEqual(run(["bash", self.script, "--keep", "x"]).returncode, 1)
        self.assertEqual(run(["bash", self.script, "--dir", "/"]).returncode, 1)
        self.assertEqual(run(["bash", self.script, "--host"]).returncode, 1)

    def test_help_lists_the_options(self):
        proc = run(["bash", self.script, "--help"])
        self.assertEqual(proc.returncode, 0)
        for option in ("--host", "--dry-run", "--rollback", "--no-restart", "--backup-dir", "--keep"):
            self.assertIn(option, proc.stdout)

    def test_version_matches_the_package(self):
        proc = run(["bash", self.script, "--version"])
        from pihole_control import __version__
        self.assertEqual(proc.stdout.strip(), __version__)


if __name__ == "__main__":
    unittest.main()
