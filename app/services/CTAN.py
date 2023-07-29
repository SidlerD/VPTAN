import logging

from datetime import date
from fastapi import HTTPException, status
import requests
from app.helpers import helpers

from app.schemas import Package

logger = helpers.make_logger('api_get_packages')


def download_pkg(pkg: Package) -> bytes:
    logger.info(f"CTAN: Downloading {pkg} {date}")
    
    # Extract download path
    if pkg.install:
        path = pkg.install
        url = "https://mirror.ctan.org/install" + path # Should end in .zip or similar
    
    elif pkg.ctan:
        path = pkg.ctan.path
        url = f"https://mirror.ctan.org/tex-archive/{path}{'' if '.' in path else '.zip' }"
    else:
        if pkg.id:
            raise HTTPException(status_code=400, detail={'reason': f"{pkg.id} is not downloadable", 'CTAN_response': pkg})
        raise HTTPException(status_code=400, detail={'reason': f"{pkg.id} not available on CTAN", 'CTAN_response': pkg})
    
    logger.debug(f"CTAN download-url is {url}")
    
    if url.endswith('.zip'):
        response = requests.get(url, allow_redirects=True)
        if not response.ok:
            raise HTTPException(400, response.reason)

        return response.content
    else:
        return helpers.download_files_to_binary_zip([url], pkg.id)

    