import logging

from datetime import date
from fastapi import HTTPException, status
import requests

from app.schemas import Package

logger = logging.getLogger("default")

def download_pkg(pkg: Package) -> bytes:
    print(f"CTAN: Downloading {pkg} {date}")
    
    # Extract download path
    if pkg.install:
        path = pkg.install
        url = "https://mirror.ctan.org/install" + path # Should end in .zip or similar
    
    elif pkg.ctan:
        path = pkg.ctan.path
        url = f"https://mirror.ctan.org/tex-archive/{path}.zip"
    else:
        if pkg.id:
            raise HTTPException(status_code=400, detail={'reason': f"{pkg.id} is not downloadable", 'CTAN_response': pkg})
        raise HTTPException(status_code=400, detail={'reason': f"{pkg.id} not available on CTAN", 'CTAN_response': pkg})

    response = requests.get(url, allow_redirects=True)
    if not response.ok:
        raise HTTPException(400, response.reason)

    return response.content