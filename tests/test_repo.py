"""Repository hygiene: versions agree, docs are current, links resolve, scripts are executable."""
import glob
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

from pihole_control import __version__  # noqa: E402
from pihole_control.constants import PLUGIN_KEY, STAT_DEVICES  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def source_text():
    """plugin.py and the package, as one string."""
    paths = [os.path.join(ROOT, "plugin.py")] + sorted(glob.glob(os.path.join(ROOT, "pihole_control", "*.py")))
    out = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            out.append(fh.read())
    return "\n".join(out)


class VersionTests(unittest.TestCase):
    def test_version_is_plain_numeric(self):
        # plugin managers (PyPluginStore) only recognise plain numeric tags: no -alpha / -rc suffix
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+(\.\d+)?$")

    def test_plugin_manifest_matches_package(self):
        match = re.search(r'<plugin\b[^>]*\bversion="([^"]+)"', read("plugin.py"))
        self.assertIsNotNone(match, "no version in the plugin manifest")
        self.assertEqual(match.group(1), __version__)

    def test_plugin_key_is_the_one_of_the_installed_base(self):
        # changing the key would turn every existing installation into an unknown hardware type
        match = re.search(r'<plugin\b[^>]*\bkey="([^"]+)"', read("plugin.py"))
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), PLUGIN_KEY)
        self.assertEqual(PLUGIN_KEY, "PiHole")

    def test_changelog_top_entry_matches_package(self):
        headings = re.findall(r"^## \[([^\]]+)\]", read("CHANGELOG.md"), re.M)
        released = [h for h in headings if h.lower() != "unreleased"]
        self.assertTrue(released, "CHANGELOG.md has no released version")
        self.assertEqual(released[0], __version__, "newest CHANGELOG entry differs from pihole_control.__version__")

    def test_changelog_links_every_release(self):
        text = read("CHANGELOG.md")
        for version in re.findall(r"^## \[(\d[^\]]*)\]", text, re.M):
            self.assertRegex(text, r"(?m)^\[%s\]: https?://" % re.escape(version))

    def test_changelog_release_link_points_at_this_repository(self):
        self.assertIn("https://github.com/janreimen/Domoticz-PiHole-Control/releases/tag/v%s" % __version__,
                      read("CHANGELOG.md"))


class FileTests(unittest.TestCase):
    REQUIRED = ["LICENSE", "NOTICE", "README.md", "CHANGELOG.md", "ROADMAP.md", "SECURITY.md", "CONTRIBUTING.md",
                "DEPLOY.md", "ACCESSIBILITY.md", "checklist.md", "Makefile", "deploy.sh", "requirements.txt",
                ".gitignore", ".github/workflows/tests.yml", ".github/CODE_OF_CONDUCT.md",
                ".github/PULL_REQUEST_TEMPLATE.md", ".github/ISSUE_TEMPLATE/config.yml",
                ".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/feature_request.yml",
                "docs/DEVICES.md", "docs/PIHOLE-API.md", "tools/gen_device_catalog.py"]

    def test_required_files_exist(self):
        missing = [p for p in self.REQUIRED if not os.path.exists(os.path.join(ROOT, p))]
        self.assertEqual(missing, [])

    def test_readme_has_the_lowercase_name_only(self):
        names = os.listdir(ROOT)
        self.assertIn("README.md", names)
        self.assertNotIn("README.MD", names)        # the old file name: it would be a second README on Linux

    @unittest.skipIf(os.name != "posix", "POSIX permissions")
    def test_scripts_are_executable(self):
        for path in ("deploy.sh", "tools/gen_device_catalog.py"):
            self.assertTrue(os.access(os.path.join(ROOT, path), os.X_OK), path + " is not executable")

    def test_markdown_links_resolve(self):
        docs = [p for p in os.listdir(ROOT) if p.endswith(".md")]
        docs += [".github/CODE_OF_CONDUCT.md", ".github/PULL_REQUEST_TEMPLATE.md"]
        docs += ["docs/" + p for p in os.listdir(os.path.join(ROOT, "docs")) if p.endswith(".md")]
        broken = []
        for doc in docs:
            base = os.path.dirname(os.path.join(ROOT, doc))
            for target in re.findall(r"\]\(([^)\s]+)\)", read(doc)):
                if re.match(r"^(https?:|mailto:|#)", target):
                    continue
                path = target.split("#", 1)[0]
                if path and not os.path.exists(os.path.normpath(os.path.join(base, path))):
                    broken.append("%s -> %s" % (doc, target))
        self.assertEqual(broken, [])

    def test_readme_anchors_used_by_other_documents_exist(self):
        def slug(heading):
            heading = re.sub(r"[`*]", "", heading).strip().lower()
            heading = re.sub(r"[^\w\- ]", "", heading)
            return heading.replace(" ", "-")

        anchors = {slug(h) for h in re.findall(r"^#{1,6} (.+)$", read("README.md"), re.M)}
        wanted = set()
        for doc in os.listdir(ROOT):
            if doc.endswith(".md"):
                wanted.update(re.findall(r"\]\(README\.md#([^)\s]+)\)", read(doc)))
        wanted.update(re.findall(r"\]\(#([^)\s]+)\)", read("README.md")))
        self.assertEqual(sorted(wanted - anchors), [], "links to README sections that do not exist")

    def test_readme_uses_the_real_directory_name(self):
        text = read("README.md") + read("DEPLOY.md")
        self.assertIn("Domoticz-PiHole-Control", text)
        self.assertIn("git clone https://github.com/janreimen/Domoticz-PiHole-Control.git", text)

    def test_nothing_is_left_over_from_the_plugins_this_one_was_modelled_on(self):
        pattern = re.compile(r"synosnmp|synology|snmp|openaq|myskoda", re.I)
        found = []
        for path in (glob.glob(os.path.join(ROOT, "*.md")) + glob.glob(os.path.join(ROOT, "*.sh"))
                     + [os.path.join(ROOT, "Makefile")] + glob.glob(os.path.join(ROOT, "pihole_control", "*.py"))
                     + glob.glob(os.path.join(ROOT, "docs", "*.md")) + glob.glob(os.path.join(ROOT, ".github", "**", "*"),
                                                                                  recursive=True)):
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    if pattern.search(fh.read()):
                        found.append(os.path.relpath(path, ROOT))
        self.assertEqual(found, [])


class DocumentationTests(unittest.TestCase):
    def test_troubleshooting_messages_exist_in_the_code_and_in_the_readme(self):
        # the README quotes log messages: if one is reworded in the code, the table must follow
        fragments = ["No Pi-hole password configured", "must start with http:// or https://",
                     "Certificate chain file not found", "Login rejected", "Check the certificate chain file",
                     "use that address as Pi-hole URL", "no answer within", "No free Domoticz unit left",
                     "Cannot update Domoticz unit", "still reports", "Unexpected error in", "Pi-hole poll failed",
                     "Domoticz did not create the device", "Accept new Hardware Devices"]
        code, readme = source_text(), read("README.md")
        for fragment in fragments:
            self.assertTrue(fragment in code, "no longer in the code: " + fragment)
            self.assertTrue(fragment in readme, "not in the README troubleshooting table: " + fragment)

    def test_deploy_guide_quotes_the_start_up_messages_the_code_writes(self):
        code, deploy = source_text(), read("DEPLOY.md")
        for fragment in ("Connected to the Pi-hole at", "starting for", "Command received:"):
            self.assertTrue(fragment in code, "no longer in the code: " + fragment)
            self.assertTrue(fragment in deploy, "not in DEPLOY.md: " + fragment)
        # "... is now enabled / disabled" is built from two parts in the code
        self.assertTrue("is now %s" in code and '"enabled" if enabled else "disabled"' in code)
        self.assertTrue("is now enabled" in deploy)

    def test_readme_names_the_hardware_type_of_the_manifest(self):
        name = re.search(r'<plugin\b[^>]*\bname="([^"]+)"', read("plugin.py")).group(1)
        self.assertIn(name, read("README.md"))
        self.assertIn(name, read("DEPLOY.md"))

    def test_readme_unit_ranges_match_the_code(self):
        from pihole_control import constants as c
        readme = read("README.md")
        self.assertIn("%d - %d" % (c.LIST_UNIT_FIRST, c.LIST_UNIT_LAST), readme)
        self.assertIn("%d - %d" % (c.GROUP_UNIT_FIRST, c.GROUP_UNIT_LAST), readme)
        self.assertIn("%d - %d" % (c.MIN_INTERVAL, c.MAX_INTERVAL), readme.replace("to", "-"))


class GeneratedDocsTests(unittest.TestCase):
    def test_device_catalogue_is_up_to_date(self):
        import gen_device_catalog
        self.assertEqual(read("docs", "DEVICES.md"), gen_device_catalog.render(),
                         "docs/DEVICES.md is stale: run python3 tools/gen_device_catalog.py")

    def test_every_statistics_device_has_a_documented_source(self):
        import gen_device_catalog
        missing = [spec.key for spec in STAT_DEVICES if spec.key not in gen_device_catalog.SOURCES]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
