from collections import defaultdict
import io
import os
from os.path import abspath, basename, join
import re
import subprocess
import zipfile

import requests

from app.schemas import Package


reg_patterns = {
    'pkg': {'reg': r'\\ProvidesPackage\s*\{(.*?)\}\s*(?:\[([\S\s]*?)\])?', 'version': 2, 'name': 1},  # Group 1=name, 2=version
    'cls': {'reg': r'\\ProvidesClass\s*\{(.*?)\}[^\[]*([\S\s]*?)\]', 'version': 2, 'name': 1}, 
    'expl_pkg': {'reg': r'\\ProvidesExplPackage\s*\{(.*?)(?:\..*)?\}\s*\{(.*?)(?:\..*)?\}\s*\{(.*?)(?:\..*)?\}\s*\{(.*?)(?:\..*)?\}', 'version': 2, 'name': 1},  # Group 1=name, 2=date, 3=version, 4=description
    'file': {'reg': r'\\ProvidesFile\s*\{(.*?)\}\s*\[(.*?)\]', 'version': 2, 'name': 1}  # Group 1=name, 2=version

}


def download_files_to_binary_zip(file_urls: "list[str]", pkg_id: str) -> bytes:
    zip_filename = "%s.zip" % pkg_id

    s = io.BytesIO()
    zf = zipfile.ZipFile(file=s, mode="w")

    for url in file_urls:
        # Calculate path for file in zip
        fname = os.path.basename(url).split('?')[0]
        if not fname: # E.g. hyperref, which has /doc folder
            continue

        resp = requests.get(url)
        if not resp.ok:
            raise RuntimeError("Couldnt get file at " + url)
        
        # Add file, at correct path
        zf.writestr(data=resp.content, zinfo_or_arcname = fname)

    # Must close zip for all contents to be written
    zf.close()

    print(f"Successfully built zip-file, returning it now")

    # Grab ZIP file from in-memory, return
    return s.getvalue()


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

