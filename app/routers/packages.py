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
    if not (date or number) or check_satisfying(ctan_pkg.version, req_version):
        return StreamingResponse(io.BytesIO(CTAN.download_pkg(ctan_pkg)))

    return TL.download_pkg(ctan_pkg, req_version)


def check_satisfying(ctan: Version, req: Version):
    if not isinstance (ctan.date, date):
        if type(ctan.date) == str:
            ctan.date = valid_date(ctan.date)
    if not isinstance (req.date, date):
        if type(req.date) == str:
            req.date = valid_date(req.date)
    
    # TODO: Could break up more to give the reason why they're not equal
    if ctan.date == req.date and ctan.number == req.number:
        return True
    return False