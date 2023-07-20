from fastapi import APIRouter

router = APIRouter(
    prefix="/packages",
    tags=["packages"],
        responses={404: {"description": "Not found"}},
)

@router.get("/")
def getAllPackages():
    return {'message': 'Go to /<package-id> to get the files for package-id'}