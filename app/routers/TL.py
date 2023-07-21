import logging

from datetime import date
from fastapi import HTTPException, status
import requests

from app.schemas import Package, Version

logger = logging.getLogger("default")

def download_pkg(pkg: Package, version: Version):
    print(f"TL: Downloading {pkg.id} {version}")
    

    
    # return response.content