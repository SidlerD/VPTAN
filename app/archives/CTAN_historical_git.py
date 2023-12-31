import datetime
from typing import Optional
from app.archives.IArchive import IArchive
from app.helpers import helpers
from app.schemas import Package

from dateutil import parser
import logging
import os
from os.path import join, isdir, isfile, basename, exists
import subprocess
import requests
import json
from bs4 import BeautifulSoup as bs4
from urllib.parse import urljoin
from collections import defaultdict


class CTAN_historical_git(IArchive):
    def __init__(self, ctan_archive_path='CTAN') -> None:
        self._ctan_path = os.path.normpath(ctan_archive_path)
        # self._ctan_path = Path(ctan_archive_path)
        self._pkg_info_file = "CTAN_packages.json"
        self._index_file = "CTAN_Archive_index.json"
        self._pkg_infos = self._get_pkg_infos()
        self._index = self._read_index_file()
        self._index_logger = helpers.make_logger(name='CTANArchive')
        self._download_logger = helpers.make_logger(name='api_get_packages')

    def update_index(self, inspect_every_nth_commit: int = 7):
        self._index_logger.info("Updating index")
        old_cwd = os.getcwd()
        os.chdir(self._ctan_path)

        try:
            # Checkout master (Restores HEAD to latest commit, otherwise getting list of all commits not possible)
            curr_branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).decode().strip()
            if curr_branch != 'master':
                subprocess.call(['git', 'checkout', '--force', 'master'])  # Checkout the commit

            # TODO: Pull latest changes here

            commit_hashes = subprocess.check_output(
                ['git', 'rev-list', 'HEAD'], cwd=self._ctan_path).decode().splitlines()
            indexed_commit_hashes = [hash for hash in self._index.keys()]

            # Only build index for hashes which are not yet in index
            hashes_to_index = [hash for hash in commit_hashes if hash not in indexed_commit_hashes]

            if len(hashes_to_index) == 0:
                self._index_logger.info("Index is already up-to-date")
                os.chdir(old_cwd)
                return
            self._index_logger.info(f"Adding {len(hashes_to_index)} hashes to index: {hashes_to_index}")

            for i, commit_hash in enumerate(hashes_to_index):
                # For every n-th commit, ...
                if i % inspect_every_nth_commit == 0:
                    subprocess.call(['git', 'stash'])  # stash any changes,
                    subprocess.call(['git', 'checkout', '--force', commit_hash])  # checkout the commit and
                    try:
                        self._build_index_for_hash(commit_hash)  # Build the index for current hash
                    except Exception as e:
                        self._index_logger.error(f"unexpected error at commit {commit_hash}: {e}")
                        logging.exception(e)
                else:
                    self._index[commit_hash] = None
                    self._index_logger.info(f"Skipping commit {commit_hash}")

            self._index_logger.info("All commit-hashes done")

        except Exception as e:
            self._index_logger.error(str(e))
            logging.exception(e)

        os.chdir(old_cwd)
        self._write_index_to_file()

    def get_commit_hash(self, pkg: Package, closest: bool) -> Optional[str]:
        """Get commit hash at which pkg has the correct version in git archive"""
        all_versions = []

        for hash in self._index:
            if not self._index[hash] or not self._index[hash][pkg.id]:
                continue
            files = self._index[hash][pkg.id]
            if 'Error' in files.keys():
                continue
            if len(files) != 1:
                self._index_logger.info(f"{pkg.id} has {len(files)} files with a version: {files.values()}. Returning first one")  # noqa: E501
            if closest:
                all_versions.append({hash: files})
                continue

            for version in files.values():
                if helpers.version_matches(version, pkg.version):
                    self._index_logger.info(f"{pkg.id} has version {pkg.version} at commit {hash}")
                    return hash

        if closest and all_versions and pkg.version.date:
            def get_date_from_pair(pair: dict):
                # ASSUMPTION: Every file for one package at one commit hash has same version
                file = pair[next(iter(pair))]
                if 'Error' in file:
                    return ''
                version = file[next(iter(file))]
                date = version['date']
                return date if isinstance(date, datetime.date) else parser.parse(date).date()

            req_date = pkg.version.date
            all_versions_clean = [{next(iter(pair)): get_date_from_pair(pair)} for pair in all_versions]

            # later_versions = filter(lambda pair: self.get_date_from_pair(pair) >= req_date, all_versions)
            # closest_later = min(later_versions, key = lambda pair: self.get_date_from_pair(pair))
            later_versions = filter(lambda pair: pair[next(iter(pair))] >= req_date, all_versions_clean)
            closest_later = min(later_versions, key=lambda pair: pair[next(iter(pair))])

            self._download_logger.info(f"For {pkg.id}({pkg.version.date}): Closest version is {closest_later}")
            return next(iter(closest_later))
        return None

        # TODO: Could check the date of each commit in archive, and then take the hash which is one day after req_date
        # https://stackoverflow.com/questions/50452866/how-to-show-date-and-time-of-a-commit-by-hash#:~:text=git%20show%20%2D%2Dno%2Dpatch%20%2D%2Dno%2Dnotes%20%2D%2Dpretty%3D%27%25cd%27%20fe1ddcdef

    def _get_pkg_infos(self):
        # ASSUMPTION: Every package's files are stored in a folder with pkg_name
        if not exists(self._pkg_info_file):
            all = requests.get("http://www.ctan.org/json/2.0/packages").json()

            res = []
            for pkg in all:
                pkg_id = pkg['key']

                pkgInfo_res = requests.get(f"https://www.ctan.org/json/2.0/pkg/{pkg_id}")
                if not pkgInfo_res.ok:
                    print(f"{pkg['name']} not on CTAN")
                    continue
                pkgInfo = pkgInfo_res.json()
                res.append(Package(**pkgInfo))

            with open(self._pkg_info_file, "w", encoding='utf-8') as f:
                json.dump(res, f, default=lambda elem: elem.__dict__)
        else:
            with open(self._pkg_info_file, "r", encoding='utf-8') as f:
                data = json.load(f)
                res = [Package(**pkginfo) for pkginfo in data]

        return res

    def _read_index_file(self):
        def defaultdict_from_dict(d):
            nd = lambda: defaultdict(nd)  # noqa: E731
            ni = nd()
            ni.update(d)
            return ni

        if exists(self._index_file):
            with open(self._index_file, 'r') as f:
                return json.load(f, object_hook=defaultdict_from_dict)
        else:
            with open(self._index_file, 'w') as f:
                json.dump({}, f)
            return defaultdict(lambda: defaultdict(dict))

    def _write_index_to_file(self):
        try:
            with open(self._index_file, "w") as indexf:
                json.dump(self._index, indexf, indent=2)

        except Exception as e:
            logging.exception(e)
            # print(self._index)
            with open(self._index_file, "w") as indexf:
                indexf.write(json.dumps(self._index, default=lambda elem: str(elem), indent=2))

        self._index_logger.info("Wrote index to file")

    def _build_index_for_hash(self, commit_hash):
        """Extracts versions for all packages that changed at 7 \
            or less days before specified commit, write results to index"""
        curr_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('ascii').strip()
        if curr_hash != commit_hash:
            raise ValueError(f"Building index for {commit_hash}, but git-repo is at {curr_hash}")

        changed_files = helpers.parse_changed_files(self._ctan_path)
        changed_dirs = set(os.path.split(file)[0] for file in changed_files)
        self._index_logger.info(f"Building index for {commit_hash}. {len(changed_dirs)} changed dirs")

        # Make sure we can write to index at commit hash
        if not self._index[commit_hash]:
            self._index[commit_hash] = defaultdict(lambda: defaultdict(dict))
        for pkg in self._pkg_infos:  # For each package:
            if not pkg.ctan or not pkg.ctan.path:
                self._index_logger.debug(f"{pkg.id} has no path on ctan. Skipping")
                continue
            pkg.ctan.path = pkg.ctan.path.lstrip(os.path.sep)
            pkg_dir = join(self._ctan_path, pkg.ctan.path)

            # Skip packages that haven't changed, except for first commit
            if len(self._index) > 1:
                if isfile(pkg_dir) and pkg.ctan.path not in changed_files:
                    self._index_logger.debug(f"{pkg.id} has not changed")
                    continue
                if isdir(pkg_dir) and pkg.ctan.path not in changed_dirs:
                    self._index_logger.debug(f"{pkg.id} has not changed")
                    continue

            found = False

            if not exists(pkg_dir):
                self._index_logger.debug(f"{pkg.id} should be at {pkg_dir}, which doesn't exist.")
                # self._index[commit_hash][pkg.id]["Error"] = f"{pkg.id} should be at {pkg_dir}, which doesn't exist."
                continue

            # Case where Ctan.path is a file, not a folder
            if isfile(pkg_dir):
                # pkg.ctan.path can be path to a file (e.g. /biblio/bibtex/contrib/misc/aaai-named.bst for aaai-named):
                # In this case, only look at that one file
                found = helpers.extract_version_from_file(pkg_dir, pkg.id, self._index, commit_hash)
                if not found:
                    self._index[commit_hash][pkg.id]["Error"] = f"{pkg.id} has path {pkg_dir}, which has no version"
                continue

            # TODO: Add fallback to glob-search here

            # See if pkg_id.sty or pkg_id.cls exists (Can be nested in dirs)
            relevant_files = helpers.get_relevant_files(pkg_dir, pkg)

            # Try to extract versions from pkg_name.sty/.cls
            for file in relevant_files['sty/cls']:
                found = found or helpers.extract_version_from_file(file, pkg.id, self._index, commit_hash)

            if found:
                continue

            # No files to reliably extract version from

            # Install each ins-file and check for pkg_name.sty/.cls
            for ins_file in relevant_files['ins']:
                try:
                    helpers.install_file(ins_file)
                except Exception as e:
                    self._index_logger.warning(f'Problem while installing {ins_file}: {e}')
                    continue

                _relevant_files = helpers.get_relevant_files(pkg_dir, pkg, sty_cls=True, ins=False, dtx=False)
                # Try to extract versions from pkg_name.sty/.cls
                for file in _relevant_files['sty/cls']:
                    found = found or helpers.extract_version_from_file(file, pkg.id, self._index, commit_hash)

            # Dont try to install dtx-files if ins-file is present.
            # This can lead to timeout-error for every dtx-file, which can be many (e.g. acrotex)
            if found or relevant_files['ins']:
                continue

            # Look at dtx files and try installing them
            for dtx_file in relevant_files['dtx']:
                try:
                    helpers.install_file(dtx_file)
                except Exception as e:
                    self._index_logger.warning(f'Problem while installing {dtx_file}: {e}')
                _relevant_files = helpers.get_relevant_files(pkg_dir, pkg, sty_cls=True, ins=False, dtx=False)
                # Try to extract versions from pkg_name.sty/.cls
                for file in _relevant_files['sty/cls']:
                    found = found or helpers.extract_version_from_file(file, pkg.id, self._index, commit_hash)

            if not found:
                self._index_logger.info(f'WARNING: Couldnt find any version for {pkg.name}. '
                                        f'Files: {[basename(file) for file in os.listdir(pkg_dir)]}')
                self._index[commit_hash][pkg.id]["Error"] = "No version found"

    def get_pkg_files(self, pkg: Package, closest: bool) -> bytes:
        """Returns zip-file of package's files in byte format"""
        if not pkg.ctan or not pkg.ctan.path:
            raise NotImplementedError("Can only download packages where I know the ctan path")

        # Build url where package files are found
        base_url = "https://git.texlive.info/CTAN/plain"
        commit_hash = self.get_commit_hash(pkg, closest)
        if not commit_hash:
            self._download_logger.debug(f"{pkg.id} ({pkg.version}) is not in CTAN Archive")
            return False

        overview_url = f"{base_url}{pkg.ctan.path}?id={commit_hash}"
        self._download_logger.info(f"CTAN Archive: Downloading {pkg.id} ({pkg.version}) from {overview_url}")

        # Extract download-links for each individual file
        page = requests.get(overview_url)
        soup = bs4(page.content, "html.parser")
        a_tags = soup.select("ul a")
        urls = [urljoin(base_url, elem['href']) for elem in a_tags if elem.text != "../"]

        # FIXME: Some packages follow TDS: Need to expand '/tex' and/or '/latex' to get files
        # Download each file, return as binary zip-file
        self._download_logger.info(f"Downloading {len(urls)} files from {overview_url}")
        return helpers.download_files_to_binary_zip(urls, pkg.id)


if __name__ == '__main__':
    hist = CTAN_historical_git(ctan_archive_path="/root/CTAN")

    hist.update_index()
