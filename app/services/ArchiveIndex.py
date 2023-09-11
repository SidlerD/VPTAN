import io
import logging

from fastapi import HTTPException
from app.archives.CTAN_historical_git import CTAN_historical_git

from app.schemas import Package

logger = logging.getLogger("default")

CTAN_hist = CTAN_historical_git()
def download_pkg(pkg: Package, closest: bool):
    """Checks supported package-archives for requested package, returns zipfile of package's files"""
    res = CTAN_hist.get_pkg_files(pkg, closest)
    if res:
        return res
    
    raise HTTPException(status_code=404, detail=f"{pkg.name} is not available in version {pkg.version} on VPTAN")
