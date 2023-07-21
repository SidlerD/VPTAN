from datetime import date
import io
from typing import Union
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import requests

from app.routers import CTAN, TL
from ..dependencies import pkg_id_exists, valid_date
from app.schemas import Package, Version

router = APIRouter(
    prefix="/packages",
    tags=["packages"],
        responses={404: {"description": "Not found"}},
)

@router.get("/")
def getAllPackages():
    return {'message': 'Go to /<package-id> to get the files for package-id'}

#TODO: Validate number (probably with regex)
@router.get("/{pkg_id}")
def get_package(ctan_pkg: Package = Depends(pkg_id_exists), date: Union[date, None] = Depends(valid_date), number: Union[str, None] = None):
    req_version = Version(number=number, date=date)
     
     # If version = latest or requested version equal to version on CTAN: Download from CTAN
    if check_satisfying(ctan_pkg.version, req_version):
        return StreamingResponse(io.BytesIO(CTAN.download_pkg(ctan_pkg)))

    return TL.download_pkg(ctan_pkg, req_version)


def check_satisfying(ctan_version: Version, req_version: Version):
    if not (req_version.date or req_version.number): # Call doesn't specify version
        return True
    if ctan_version == None: # CTAN has no version, but call wants specific version
        return False
    # if not isinstance (ctan_version.date, date):
    #     if type(ctan_version.date) == str:
    #         ctan_version.date = valid_date(ctan_version.date)
    # if not isinstance (req_version.date, date):
    #     if type(req_version.date) == str:
    #         req_version.date = valid_date(req_version.date)
    
    # TODO: Could break up more to give the reason why they're not equal
    if ctan_version.date == req_version.date and ctan_version.number == req_version.number:
        return True
    return False