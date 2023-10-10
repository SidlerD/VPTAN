from datetime import date
import json
import os
from fastapi import APIRouter, Depends, Response, HTTPException, status
from app.archives.CTAN_historical_git import CTAN_historical_git
from app.helpers import helpers
from os.path import join, exists, isfile, isdir, basename

logger = helpers.make_logger('search')
aliases_file = 'CTAN_aliases.json'
search_mapping_file = 'files_in_packages.json'

router = APIRouter(
    prefix="/search",
    tags=["search"],
)

@router.get("/")
def getAlias(filename: str):
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please provide a filename to search for")
    return search_for_file(filename)


def search_for_file(filename: str):
    with open(search_mapping_file, 'r') as f:
        index = json.load(f)

    occurences = []
    for pkg_id in index:
        if filename in index[pkg_id]:
            occurences.append(pkg_id)
    
    return occurences


def _build_files_in_packages(ctan_dir: str = 'CTAN'):
    """
    This function can be used to build a file that maps
    filenames to packages, which looks like this:

    {
        "pkgA": ["pkgA.sty", "pkgB.sty"],

        "pkgF": [],

        "pkgN": ["pkgA.sty", "pkg4.sty"]
     }
    """
    index = {}
    git_archive_index = CTAN_historical_git()
    pkgs = git_archive_index._pkg_infos

    for pkg in pkgs:
        if not hasattr(pkg, 'ctan'):
            continue
        
        pkg_dir = join(ctan_dir, pkg.ctan.path)
        if not exists(pkg_dir):
            print(f"{pkg_dir} is not a valid directory")
            continue

        if isdir(pkg_dir):
            index[pkg.id] = os.listdir(pkg_dir)
        elif isfile(pkg_dir):
            index[pkg.id] = basename(pkg_dir)
    
    with open(search_mapping_file, 'w') as f:
        json.dump(index, f)

            
if __name__ == '__main__':
    _build_files_in_packages()
