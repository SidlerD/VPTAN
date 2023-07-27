from app.archives.IArchive import IArchive
from app.helpers import helpers
from app.schemas import Package, Version

import logging
import os
from os.path import abspath, join, isdir, isfile, basename, exists
from os import listdir
import re
import subprocess
import requests
import json
from bs4 import BeautifulSoup as bs4
from urllib.parse import urljoin
from collections import defaultdict

class CTAN_Archive(IArchive):
    def __init__(self, ctan_archive_path = 'CTAN') -> None:
        self._ctan_path = os.path.normpath(ctan_archive_path)
        # self._ctan_path = Path(ctan_archive_path)
        self._pkg_info_file = "CTAN_packages.json"
        self._index_file = "CTAN_Archive.index.json"
        self._pkg_infos = self._get_pkg_infos()
        self._index = self._read_index_file()
        self._logger = logging.getLogger('archives')

    def update_index(self):
        try:
            commit_hashes = subprocess.check_output(['git', 'rev-list', 'HEAD']).decode().splitlines()
            indexed_commit_hashes = self._index.keys()

            hashes_to_index = [hash for hash in commit_hashes if hash not in indexed_commit_hashes]
            self._logger.info(f"Adding {len(hashes_to_index)} hashes to index: {hashes_to_index}")

            self.build_index(hashes_to_index)
        except Exception as e:
            self._logger.error(str(e))
            logging.exception(e)

    def get_commit_hash(self, pkg: Package):
        return "2d6f89f83b7567136c3a40b3b55f9be1e06bd99e"

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
            nd = lambda: defaultdict(nd)
            ni = nd()
            ni.update(d)
            return ni
        
        if exists(self._index_file):
            with open(self._index_file, 'r') as f:
                return json.load(f, object_hook=defaultdict_from_dict)
        else:
            with open(self._index_file, 'w') as f :
                json.dump({}, f)
            return defaultdict(lambda: defaultdict(dict))

    def _write_index_to_file(self):
        try:
            with open(self._index_file, "w") as indexf:
                json.dump(self._index, indexf)

        except Exception as e:
            logging.exception(e)
            # print(self._index)
            with open(self._index_file, "w") as indexf:
                indexf.write(json.dumps(self._index, default=lambda elem: elem.__dict__))
        
        self._logger.info("Wrote index to file")

    def _build_index_for_hash(self, commit_hash):
        """"""
        for pkg in self._pkg_infos: # For each package:
            pkg_dir = None
            found = False
            if pkg.ctan and pkg.ctan.path:
                subdir = os.path.normpath(pkg.ctan.path).lstrip(os.path.sep) 
                pkg_dir = join(self._ctan_path, subdir)
            if not pkg_dir or not exists(pkg_dir):
                print(f"Couldn't find {pkg.name} anywhere in {pkg_dir if pkg_dir else self._ctan_path}")
                self._index[commit_hash][pkg.id]["Error"] = "Not found in git-archive"
                continue
            elif not isdir(pkg_dir) and isfile(pkg_dir):
                # pkg.ctan.path can be path to a file (e.g. /biblio/bibtex/contrib/misc/aaai-named.bst for aaai-named): In this case, only look at that one file
                found = helpers.extract_version_from_file(pkg_dir, pkg.id, self._index, commit_hash)
                if not found:
                    self._index[commit_hash][pkg.id]["Error"] = f"{pkg.id} has path {pkg_dir}, which has no version"
                continue

            # TODO: Add fallback to glob-search here

            # See if pkg_id.sty or pkg_id.cls exists (Can be nested in dirs)
            relevant_files = helpers.get_relevant_files(pkg_dir, pkg)

            # Try to extract versions from pkg_name.sty/.cls
            for file in relevant_files['sty/cls']:
                found = helpers.extract_version_from_file(file, pkg.id, self._index, commit_hash)

            if found:
                continue

            # No files to reliably extract version from

            # Install each ins-file and check for pkg_name.sty/.cls
            for ins_file in relevant_files['ins']:
                try:
                    helpers.install_file(ins_file)
                except Exception as e:
                    print(f'Problem while installing {ins_file}: {e}')
                    continue

                _relevant_files = helpers.get_relevant_files(pkg_dir, pkg, sty_cls=True, ins=False, dtx=False)
                # Try to extract versions from pkg_name.sty/.cls
                for file in _relevant_files['sty/cls']:
                    found = helpers.extract_version_from_file(file, pkg.id, self._index, commit_hash)

                if found:
                    break
            
            if found or relevant_files['ins']: # Dont try to install dtx-files if ins-file is present. This can lead to timeout-error for every dtx-file, which can be many (e.g. acrotex)
                continue

            # Look at dtx files and try installing them
            for dtx_file in relevant_files['dtx']:
                try:
                    helpers.install_file(dtx_file)
                except Exception as e:
                    print(f'Problem while installing {dtx_file}: {e}')
                _relevant_files = helpers.get_relevant_files(pkg_dir, pkg, sty_cls=True, ins=False, dtx=False)
                # Try to extract versions from pkg_name.sty/.cls
                for file in _relevant_files['sty/cls']:
                    found = helpers.extract_version_from_file(file, pkg.id, self._index, commit_hash)

                if found:
                    break
            
            if not found:
                print(f'WARNING: Couldnt find any version for {pkg.name}. Files: {[basename(file) for file in os.listdir(pkg_dir)]}')
                self._index[commit_hash][pkg.id]["Error"] = "No version found"

    def build_index(self, hashes: "list[str]" = None):
        old_cwd = os.getcwd()
        
        try:
            os.chdir(self._ctan_path)

            # Get a list of all commit hashes
            commit_hashes = hashes or subprocess.check_output(['git', 'rev-list', 'HEAD']).decode().splitlines()
            print(commit_hashes)

            # Iterate over each commit hash
            for commit_hash in commit_hashes[:3]:
                try:
                    subprocess.call(['git', 'checkout', commit_hash])  # Checkout the commit
                except:
                    subprocess.call(['git', 'stash', commit_hash])  # stash any changes
                    subprocess.call(['git', 'checkout', '--force', commit_hash])  # Checkout the commit
                try:
                    self._build_index_for_hash(commit_hash)
                except Exception as e:
                    print(f"unexpected error at commit {commit_hash}: {e}")
                    logging.exception(e)

            print("All commit-hashes done")

        except Exception as e:
            logging.exception(e)

        os.chdir(old_cwd)
        self._write_index_to_file()

    
    def get_pkg_files(self, pkg: Package) -> bytes:
        """Returns zip-file of package's files in byte format"""
        if not pkg.ctan or not pkg.ctan.path:
            raise NotImplementedError("Can only download packages where I know the ctan path")
        
        # Build url where package files are found
        base_url = "https://git.texlive.info/CTAN/plain"
        commit_hash = self.get_commit_hash(pkg)
        overview_url =f"{base_url}{pkg.ctan.path}?id={commit_hash}"

        # Extract download-links for each individual file
        page = requests.get(overview_url)  
        soup = bs4(page.content, "html.parser")
        a_tags = soup.select("ul a")
        urls = [urljoin(base_url, elem['href']) for elem in a_tags if elem.text != "../"]

        # Download each file, return as binary zip-file
        self._logger.info(f"Downloading {len(urls)} files from {overview_url}")
        return helpers.download_files_to_binary_zip(urls, pkg.id)


if __name__ == '__main__':
    hist = CTAN_Archive(ctan_archive_path="/root/CTAN")
    # hist = CTANHistory(ctan_archive_path=r"\\wsl.localhost\UbuntuG\root\CTAN")
    hist.update_index()