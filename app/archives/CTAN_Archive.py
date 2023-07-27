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
                found = extract_version_from_file(pkg_dir, pkg.id, self._index, commit_hash)
                if not found:
                    self._index[commit_hash][pkg.id]["Error"] = f"{pkg.id} has path {pkg_dir}, which has no version"
                continue

            # TODO: Add fallback to glob-search here

            # See if pkg_id.sty or pkg_id.cls exists (Can be nested in dirs)
            relevant_files = get_relevant_files(pkg_dir, pkg)

            # Try to extract versions from pkg_name.sty/.cls
            for file in relevant_files['sty/cls']:
                found = extract_version_from_file(file, pkg.id, self._index, commit_hash)

            if found:
                continue

            # No files to reliably extract version from

            # Install each ins-file and check for pkg_name.sty/.cls
            for ins_file in relevant_files['ins']:
                try:
                    install_file(ins_file)
                except Exception as e:
                    print(f'Problem while installing {ins_file}: {e}')
                    continue

                _relevant_files = get_relevant_files(pkg_dir, pkg, sty_cls=True, ins=False, dtx=False)
                # Try to extract versions from pkg_name.sty/.cls
                for file in _relevant_files['sty/cls']:
                    found = extract_version_from_file(file, pkg.id, self._index, commit_hash)

                if found:
                    break
            
            if found or relevant_files['ins']: # Dont try to install dtx-files if ins-file is present. This can lead to timeout-error for every dtx-file, which can be many (e.g. acrotex)
                continue

            # Look at dtx files and try installing them
            for dtx_file in relevant_files['dtx']:
                try:
                    install_file(dtx_file)
                except Exception as e:
                    print(f'Problem while installing {dtx_file}: {e}')
                _relevant_files = get_relevant_files(pkg_dir, pkg, sty_cls=True, ins=False, dtx=False)
                # Try to extract versions from pkg_name.sty/.cls
                for file in _relevant_files['sty/cls']:
                    found = extract_version_from_file(file, pkg.id, self._index, commit_hash)

                if found:
                    break
            
            if not found:
                print(f'WARNING: Couldnt find any version for {pkg.name}. Files: {[basename(file) for file in os.listdir(pkg_dir)]}')
                self._index[commit_hash][pkg.id]["Error"] = "No version found"

    def build_index(self, hashes: "list[str]" = None):
        try:
            # Get a list of all commit hashes
            commit_hashes = hashes or subprocess.check_output(['git', 'rev-list', 'HEAD']).decode().splitlines()
            print(commit_hashes)

            # Iterate over each commit hash
            for commit_hash in commit_hashes:
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

        self._write_index_to_file()

    
    def get_pkg_files(self, pkg: Package) -> bytes:
        """Returns zip-file of package's files in byte format"""
        if not pkg.ctan or not pkg.ctan.path:
            raise NotImplementedError("Can only download packages where I know the ctan path")
        
        base_url = "https://git.texlive.info/CTAN/plain"
        commit_hash = self.get_commit_hash(pkg)
        overview_url =f"{base_url}{pkg.ctan.path}?id={commit_hash}"

        page = requests.get(overview_url)  
        soup = bs4(page.content, "html.parser")

        a_tags = soup.select("ul a")
        urls = [urljoin(base_url, elem['href']) for elem in a_tags if elem.text != "../"]

        self._logger.info(f"Downloading {len(urls)} files from {overview_url}")

        return helpers.write_files_to_binary_zip(urls, pkg.id)


# pkgs_path = os.path.join(repo_path, 'macros\latex')
pkgs_path = join('macros', 'latex')

reg_patterns = {
    'pkg': {'reg': r'\\ProvidesPackage\s*\{(.*?)\}\s*(?:\[([\S\s]*?)\])?', 'version': 2, 'name': 1},  # Group 1=name, 2=version
    'cls': {'reg': r'\\ProvidesClass\s*\{(.*?)\}[^\[]*([\S\s]*?)\]', 'version': 2, 'name': 1}, 
    'expl_pkg': {'reg': r'\\ProvidesExplPackage\s*\{(.*?)(?:\..*)?\}\s*\{(.*?)(?:\..*)?\}\s*\{(.*?)(?:\..*)?\}\s*\{(.*?)(?:\..*)?\}', 'version': 2, 'name': 1},  # Group 1=name, 2=date, 3=version, 4=description
    'file': {'reg': r'\\ProvidesFile\s*\{(.*?)\}\s*\[(.*?)\]', 'version': 2, 'name': 1}  # Group 1=name, 2=version

}

def get_relevant_files(subdir: str, pkg: Package, sty_cls = True, ins = True, dtx = True):
    relevant_files = {'sty/cls': [], 'ins': [], 'dtx': []}
    isolated = basename(subdir) == pkg.id or basename(subdir) == pkg.name
    """If pkg has its own folder, all dtx/ins-files should be installed. If not (e.g. trace, which is in required/tools with other packages), only files named with pkg.id or pkg.name should be installed."""
    if subdir and os.path.islink(subdir): # FIXME: This doesn't work on Windows, only on Linux
        print(subdir + " is a symlink, resolving now")
        # FIXME: For something like a4, this returns a simple folder name (i.e. relative path) instead of the full path
        subdir = os.readlink(subdir)
        print("subdir is now " + subdir)
    # Get relevant files in all subdirs. followlinks=True because for some packages, the package folder is a symlink, e.g. a4
    for path, subdirs, files in os.walk(subdir, followlinks=True):
        for file in files:
            if sty_cls and file in [f"{pkg.name}.sty", f"{pkg.name}.cls", f"{pkg.id}.sty", f"{pkg.id}.cls"]:
                relevant_files['sty/cls'].append(join(path, file))
            elif ins and (isolated and file.endswith('.ins') or not isolated and file in [f"{pkg.id}.ins",f"{pkg.name}.ins"] ):
                relevant_files['ins'].insert(0 if basename(file).startswith(pkg.name) or basename(file).startswith(pkg.id) else -1, join(path, file))
            elif dtx and (isolated and file.endswith('.dtx') or not isolated and file in [f"{pkg.id}.dtx",f"{pkg.name}.dtx"] ):
                relevant_files['dtx'].insert(0 if basename(file).startswith(pkg.name) or basename(file).startswith(pkg.id) else -1, join(path, file))
    return relevant_files

def install_file(file: str):
    # TODO: Change into dir of file here and then back out again
    path, fname = os.path.split(file)
    old_cwd = os.getcwd()
    os.chdir(abspath(path))

    try:
        if fname.endswith('.ins'):
            subprocess.run(['latex', fname], stdout=subprocess.DEVNULL, timeout=3)
        elif fname.endswith('.dtx'):
            subprocess.run(['tex',   fname], stdout=subprocess.DEVNULL, timeout=2)
        else:
            raise ValueError(f"{fname} is not an installable package-file")
    except:
        os.chdir(old_cwd)
        raise
    os.chdir(old_cwd)


def extract_version_from_file(fpath: str, pkg_id: str, index: defaultdict, commit_hash: str) -> bool:
    try:
        content, pkg_version = '', None
        # Read file
        try:
            with open(fpath, "r") as f:
                content = f.read()
        except Exception as e:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                # TODO: Find better solution, or figure out if this is good enough
                content = f.read()
                # print(f'Opened file {basename(fpath)} with errors="ignore" and encoding="utf-8". Error: {e}')
        
        if fpath.endswith('.sty'):
            for regex in [reg_patterns['pkg'], reg_patterns['expl_pkg']]:
                match = re.search(regex['reg'], content)
                if match:
                    pkg_version = match.group(regex['version']) 
                    break
        elif fpath.endswith('.cls'):
            for regex in [reg_patterns['cls'], reg_patterns['file']]:
                match = re.search(regex['reg'], content)
                if match:
                    pkg_version = match.group(regex['version']) 
                    break

        if not pkg_version:
            return False
         
        index[commit_hash][pkg_id][basename(fpath)] = pkg_version
        print(f"{pkg_id}: {pkg_version}")
        return True


    except Exception as e:
        index[commit_hash][pkg_id]["Error"] = f"{basename(fpath)}: {e}"
        print(e)
        return False



if __name__ == '__main__':
    hist = CTAN_Archive(ctan_archive_path="/root/CTAN")
    # hist = CTANHistory(ctan_archive_path=r"\\wsl.localhost\UbuntuG\root\CTAN")
    hist.build_index()