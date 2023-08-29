from datetime import date
import io
import json
import threading
from typing import Union
from fastapi import APIRouter, Depends, Response, HTTPException, status
import requests
from app.helpers import helpers
from os.path import isfile, exists, abspath
import asyncio

logger = helpers.make_logger('api_alias')
aliases_file = 'CTAN_aliases.json'
_ctan_url = "https://www.ctan.org/"

router = APIRouter(
    prefix="/alias",
    tags=["alias"],
        responses={404: {"description": "Has no alias"}},
)

@router.get("/")
def getAlias(id: Union[str, None] = None, name: Union[str, None] = None):
    if not name and not id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please provide either id or name")
    return get_alias_of_package(id, name)



def get_alias_of_package(id = '', name = '') -> dict:
    """Some packages are not available on CTAN directly, but are under another package, where they are listed as 'aliases'
    Example: tikz is not available on CTAN as package, but is listed in alias field of pgf. Therefore, we should download pgf to get tikz"""
    logger.info(f'Searching for {id if id else name} in aliases')

    found = False

    if not isfile(abspath(aliases_file)):
        with open(aliases_file, 'w') as f:
            json.dump({}, f)
    else:
        with open(aliases_file, "r") as f:
            aliases = json.load(f)
            for alias in aliases:
                if id and alias['id'] == id or name and alias['name'] == name:
                    found = True
                    break
    
    if not found:
        logger.info(f"Couldn't find {id if id else name} in list of aliases")

        background_thread = threading.Thread(target=update_aliases)
        background_thread.start()

        raise HTTPException(status_code=404, detail=f"{id if id else name} is not available on CTAN under any alias")

    return alias


# TODO: Make sure it isnt updated on every call, only if last call was e.g more than 1 day ago
def update_aliases() -> bool:
    logger.info('Updating list of aliases from CTAN. Please note that this can take very long')

    all = requests.get(f"{_ctan_url}json/2.0/packages").json()
    aliases = []

    for pkg in all:
        try:
            pkgInfo = get_package_info(pkg['key'])
            if 'aliases' in pkgInfo and pkgInfo['aliases']:
                logger.debug(pkg['key'] + ' has an alias')
                try:
                    alias_info = pkgInfo['aliases']
                    for alias in alias_info:
                        aliases.append({'name': alias['name'], 'id': alias['id'], 'aliased_by': {'id': pkg['key'], 'name': pkg['name']}})
                except Exception as e:
                    logger.warning(f'Something went wrong while extracting alias for {pkgInfo["id"]}, alias = {pkgInfo["aliases"]}: {str(e)}')
        except ValueError as e:
            print(e)
    
    with open(aliases_file, 'w') as f:
        json.dump(aliases, f, indent=2)


def get_package_info(id: str):
    pkgInfo = requests.get(f"{_ctan_url}json/2.0/pkg/{id}").json()
    if "id" not in pkgInfo or "name" not in pkgInfo:
        raise ValueError("CTAN has no information about package with id " + id)
    
    if 'ctan' not in pkgInfo or not pkgInfo['ctan']:
        raise ValueError(f"{id} is on CTAN, but not downloadable")
    
    return pkgInfo