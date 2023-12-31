from datetime import date
from typing import Union
from fastapi import APIRouter, Depends, Response, HTTPException
from app.helpers import helpers

from app.services import ArchiveService
from app.archives import CTAN
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


logger = helpers.make_logger('api_get_packages')


@router.get("/{pkg_id}")
def get_package(ctan_pkg: Package = Depends(pkg_id_exists), date: Union[date, None] = Depends(valid_date),
                number: Union[str, None] = None, closest: Union[bool, None] = None):
    req_version = Version(number=number, date=date)
    logger.info(f"/pkg_id called with {ctan_pkg.id} in version {req_version}")

    # If version = latest or requested version equal to version on CTAN: Download from CTAN
    if check_satisfying(ctan_pkg.version, req_version):
        byte_data = CTAN.download_pkg(ctan_pkg)
    else:
        try:
            ctan_pkg.version = req_version
            byte_data = ArchiveService.download_pkg(ctan_pkg, closest)
        except HTTPException:
            raise

    return Response(byte_data, media_type="application/x-zip-compressed")


def check_satisfying(ctan_version: Version, req_version: Version):
    if not (req_version.date or req_version.number):  # Call doesn't specify version
        return True
    if ctan_version is None:  # CTAN has no version, but call wants specific version
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
