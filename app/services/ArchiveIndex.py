import io
import logging

from fastapi import HTTPException
from app.archives.CTAN_Archive import CTAN_Archive

from app.schemas import Package

logger = logging.getLogger("default")

CTANArch = CTAN_Archive()
def download_pkg(pkg: Package):
    """Checks supported package-archives for requested package, returns zipfile of package's files"""
    res = CTANArch.get_pkg_files(pkg)
    if res:
        return res
    
    raise HTTPException(status_code=404, detail=f"{pkg.name} is not available in version {pkg.version}")
