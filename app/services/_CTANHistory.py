from app.schemas import Package, Version

import logging
import os
from os.path import abspath, join, isdir, isfile, basename, exists
from os import listdir
from pathlib import Path
import re
import subprocess
import requests
import json
from collections import defaultdict


def get_commit_hash(pkg: Package, version: Version):
    return "2d6f89f83b7567136c3a40b3b55f9be1e06bd99e"


repo_path = r"CTAN"
# pkgs_path = os.path.join(repo_path, 'macros\latex')
pkgs_path = join('macros', 'latex')
packages_file = r"TL_packages.json"

name_to_id = None
with open(packages_file, "r") as f:
        cont = f.read()
        name_to_id = json.loads(cont) # List of all packages on CTAN

reg_patterns = {
    'pkg': {'reg': r'\\ProvidesPackage\s*\{(.*?)\}\s*(?:\[([\S\s]*?)\])?', 'version': 2, 'name': 1},  # Group 1=name, 2=version
    'cls': {'reg': r'\\ProvidesClass\s*\{(.*?)\}[^\[]*([\S\s]*?)\]', 'version': 2, 'name': 1}, 
    'expl_pkg': {'reg': r'\\ProvidesExplPackage\s*\{(.*?)(?:\..*)?\}\s*\{(.*?)(?:\..*)?\}\s*\{(.*?)(?:\..*)?\}\s*\{(.*?)(?:\..*)?\}', 'version': 2, 'name': 1},  # Group 1=name, 2=date, 3=version, 4=description
    'file': {'reg': r'\\ProvidesFile\s*\{(.*?)\}\s*\[(.*?)\]', 'version': 2, 'name': 1}  # Group 1=name, 2=version

}

def get_packages_list():
    res = requests.get("http://www.ctan.org/json/2.0/packages").json()

    index = {}
    for pkg in res:
        # if pkg['name'] != pkg['key']:
        index[pkg['name']] = pkg['key']


    with open(packages_file, "w", encoding='utf-8') as f:
        f.write(json.dumps(index))

def find_dir(pkg_name: str) -> str:
    # ASSUMPTION: Every package's files are stored in a folder with pkg_name
    possible_subdirs = []
    for folder in ["contrib", "exptl", "required"]:
        path = join(pkgs_path, folder, pkg_name) 
        if exists(path):
            possible_subdirs.append(path)
    if len(possible_subdirs) > 0:
        return possible_subdirs[0]
    
    dirs = sorted(Path('.').glob(f'**/{pkg_name}'), key=lambda p: len(p.parts))
    if len(dirs) == 1:
        return str(dirs[0])
    elif len(dirs) == 0:
        raise Exception(f"Couldn't find folder for package {pkg_name}")
    else:
        print(f"{len(dirs)} dirs exist for {pkg_name}: {dirs}. Using {dirs[0]}")
        return dirs[0]

def extract_versions(index, commit_hash):
    """Assumes that all packages are in subfolder /macros/latex/"""
    for pkg_name in name_to_id: # For each package:
        pkg_id = name_to_id[pkg_name]
        found = False
        try:
            subdir = find_dir(pkg_name)
        except Exception as e:
            print(e)

        # See if pkg_id.sty or pkg_id.cls exists (Can be nested in dirs)
        relevant_files = get_relevant_files(subdir, pkg_name)

        # Try to extract versions from pkg_name.sty/.cls
        for file in relevant_files['sty/cls']:
            found = extract_version_from_file(file, pkg_id, index, commit_hash)

        if found:
            continue

        # No files to reliably extract version from

        # Install each ins-file and check for pkg_name.sty/.cls
        for ins_file in relevant_files['ins']:
            try:
                install_file(ins_file)
            except Exception as e:
                print(f'Problem while installing {basename(ins_file)}: {e}')
                continue

            _relevant_files = get_relevant_files(subdir, pkg_name, sty_cls=True, ins=False, dtx=False)
            # Try to extract versions from pkg_name.sty/.cls
            for file in _relevant_files['sty/cls']:
                found = extract_version_from_file(file, pkg_id, index, commit_hash)

            if found:
                break
        
        if found:
            continue

        # Look at dtx files and try installing them
        for dtx_file in relevant_files['dtx']:
            try:
                install_file(dtx_file)
            except Exception as e:
                print(f'Problem while installing {basename(dtx_file)}: {e}')
            _relevant_files = get_relevant_files(subdir, pkg_name, sty_cls=True, ins=False, dtx=False)
            # Try to extract versions from pkg_name.sty/.cls
            for file in _relevant_files['sty/cls']:
                found = extract_version_from_file(file, pkg_id, index, commit_hash)

            if found:
                break
        
        if not found:
            print(f'WARNING: Couldnt find any version for {pkg_name}')


def get_relevant_files(subdir: str, pkg_name: str, sty_cls = True, ins = True, dtx = True):
    relevant_files = {'sty/cls': [], 'ins': [], 'dtx': []}
    if os.path.islink(subdir): # FIXME: This doesn't work on Windows, only on Linux
        print(subdir + " is a symlink, resolving now")
        # FIXME: For something like a4, this returns a simple folder name (i.e. relative path) instead of the full path
        subdir = os.readlink(subdir)
        print("subdir is now " + subdir)
    # Get relevant files in all subdirs. followlinks=True because for some packages, the package folder is a symlink, e.g. a4
    for path, subdirs, files in os.walk(subdir, followlinks=True):
        for file in files:
            if sty_cls and file == f"{pkg_name}.sty" or file == f"{pkg_name}.cls":
                relevant_files['sty/cls'].append(join(path, file))
            elif ins and file.endswith('.ins'):
                relevant_files['ins'].insert(0 if basename(file).startswith(pkg_name) else -1, join(path, file))
            elif dtx and file.endswith('.dtx'):
                relevant_files['dtx'].insert(0 if basename(file).startswith(pkg_name) else -1, join(path, file))
    # Move files with name pkg_name to front of their list
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
        index[commit_hash][pkg_id][basename(fpath)] = f"ERROR: {e}"
        print(e)
        return False



if __name__ == '__main__':
    # Change directory to the repository path
    print(os.getcwd())
    os.chdir(repo_path)

    # Get a list of all commit hashes
    commit_hashes = subprocess.check_output(['git', 'rev-list', 'HEAD']).decode().splitlines()
    # print(commit_hashes)

    index = defaultdict(lambda: defaultdict(dict))

    

    # Iterate over each commit hash
    # for commit_hash in commit_hashes:
    #     try:
    #         subprocess.call(['git', 'checkout', commit_hash])  # Checkout the commit
    #     except:
    #         subprocess.call(['git', 'stash', commit_hash])  # stash any changes
    #         subprocess.call(['git', 'checkout', '--force', commit_hash])  # Checkout the commit
    #     try:
    #         extract_versions(index, commit_hash)
    #     except Exception as e:
    #         print(f"unexpected error at commit {commit_hash}: {e}")
    #         logging.exception(e)

    extract_versions(index, "commit_hash")

    print("All commit-hashes done")
    with open(r'\\wsl$\UbuntuG\root\index.json', "w") as indexf:
        indexf.write(json.dumps(index))
        print("Wrote index to file")

    # # Return to the latest commit
    # subprocess.call(['git', 'checkout', 'master'])
