#!/usr/bin/env python3

import os
import re
from typing import List

import requests
from lxml import etree

import comission.utilsCMS as uCMS
from comission.utils.logging import LOGGER
from comission.CMS.GenericCMS import GenericCMS
from comission.CMS.models.Addon import Addon
from comission.CMS.models.Vulnerability import Vulnerability


class GenericDPL(GenericCMS):
    """ Generic DRUPAL object
        This class is not intended to be instanciated as is but to be a parent for major drupal versions.
    """

    site_url = "https://www.drupal.org"
    release_site = "https://updates.drupal.org/release-history/drupal/"
    download_core_url = "https://ftp.drupal.org/files/projects/drupal-"
    base_download_addon_url = "https://ftp.drupal.org/files/projects/"
    cve_ref_url = ""

    def __init__(self, dir_path, plugins_dir, themes_dir, version="", version_major=""):
        super().__init__(dir_path, plugins_dir, themes_dir, version, version_major)

        self.addon_extension = ""

        self.regex_version_core = re.compile("version = (.*)")
        self.regex_version_addon_web = re.compile('<h2><a href="(.*?)">(.+?) (.+?)</a></h2>')
        self.regex_date_last_release = re.compile('<time pubdate datetime="(.*?)">(.+?)</time>')

        self.core.ignored_files = [
            "modules",
            "CHANGELOG.txt",
            "COPYRIGHT.txt",
            "LICENSE.txt",
            "MAINTAINERS.txt",
            "INSTALL.txt",
            "README.txt",
            "INSTALL.mysql.txt",
            "INSTALL.pgsql.txt",
            "INSTALL.sqlite.txt",
            "UPGRADE.txt",
        ]

        self.ignored_files_addon = [
            "LICENSE.txt"
        ]

    def detect_core_major_version(self) -> str:
        version_major = ""
        dpl_file_paths = {
            "8": "core/lib/Drupal.php",
            "7": "includes/bootstrap.inc"
        }

        for dpl_version, dpl_file_path in dpl_file_paths.items():
            if os.path.isfile(os.path.join(self.dir_path, dpl_file_path)):
                version_major = dpl_version

        LOGGER.debug(version_major)

        return version_major

    def get_url_release(self) -> str:
        return f"{self.release_site}{self.core.version_major}.x"

    def extract_core_last_version(self, response) -> str:
        tree = etree.fromstring(response.content)
        last_version_core = tree.xpath("/project/releases/release/tag")[0].text
        LOGGER.print_cms("info", f"[+] Last CMS version: {last_version_core}", "", 0)
        self.core.last_version = last_version_core

        return last_version_core

    def get_addon_last_version(self, addon: Addon) -> str:
        releases_url = f"{self.site_url}/project/{addon.name}/releases"

        if addon.version == "VERSION":
            addon.notes = "This is a default addon. Analysis is not yet implemented !"
            LOGGER.print_cms("alert", addon.notes, "", 1)
            return ""

        try:
            response = requests.get(releases_url, allow_redirects=False)
            response.raise_for_status()

            if response.status_code == 200:
                page = response.text

                last_version_result = self.regex_version_addon_web.search(page)
                date_last_release_result = self.regex_date_last_release.search(page)

                if last_version_result and date_last_release_result:
                    addon.last_version = last_version_result.group(3)
                    addon.last_release_date = date_last_release_result.group(2)
                    addon.link = releases_url

                    if addon.last_version == addon.version:
                        LOGGER.print_cms("good", "Up to date !", "", 1)
                    else:
                        LOGGER.print_cms(
                            "alert",
                            "Outdated, last version: ",
                            f"{addon.last_version} ({addon.last_release_date}) \n\tCheck : {releases_url}",
                            1,
                        )

        except requests.exceptions.HTTPError as e:
            addon.notes = "Addon not on official site. Search manually !"
            LOGGER.print_cms("alert", f"[-] {addon.notes}", "", 1)
            raise e
        return addon.last_version

    def get_addon_url(self, addon: Addon) -> str:
        return f"{self.base_download_addon_url}{addon.name}-{addon.version}.zip"

    def check_vulns_core(self) -> List[Vulnerability]:
        # TODO
        LOGGER.print_cms("alert", "[-] CVE check not yet implemented !", "", 0)
        return []

    def check_vulns_addon(self, addon: Addon) -> List[Addon]:
        # TODO
        LOGGER.print_cms("alert", "[-] CVE check not yet implemented !", "", 1)
        return []

    def get_archive_name(self) -> str:
        return f"drupal-{self.core.version}"

    def addon_analysis(self, addon_type: str) -> List[Addon]:
        temp_directory = uCMS.TempDir.create()
        addons = []
        addons_path = ""

        LOGGER.print_cms(
            "info",
            "#######################################################"
            + "\n\t\t"
            + addon_type
            + " analysis"
            + "\n#######################################################",
            "",
            0,
        )

        # Get the list of addon to work with
        if addon_type == "plugins":
            addons_path = self.plugins_dir

        elif addon_type == "themes":
            addons_path = self.themes_dir

        addons_name = uCMS.fetch_addons(os.path.join(self.dir_path, addons_path), "standard")

        for addon_name in addons_name:
            addon = Addon()
            addon.type = addon_type
            addon.name = addon_name
            addon.filename = addon_name + self.addon_extension

            LOGGER.print_cms("info", "[+] " + addon_name, "", 0)

            addon_path = os.path.join(self.dir_path, addons_path, addon_name)

            try:
                # Get addon version
                self.get_addon_version(addon, addon_path, self.regex_version_addon, '"')

                # Check addon last version
                self.get_addon_last_version(addon)

                # Check if there are known CVE
                self.check_vulns_addon(addon)

                # Check if the addon have been altered
                self.check_addon_alteration(addon, addon_path, temp_directory)

                addons.append(addon)
            except Exception as e:
                LOGGER.debug(str(e))
                addons.append(addon)
                pass

        if addon_type == "plugins":
            self.plugins = addons
        elif addon_type == "themes":
            self.themes = addons

        return addons
