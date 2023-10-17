import datetime as dt
from typing import Optional, Union
import pydantic


class Version(pydantic.BaseModel):
    number: Optional[str] = None
    date: Optional[Union[str, dt.date]] = None


class _Ctan(pydantic.BaseModel):
    path: str


class Package(pydantic.BaseModel):
    id: str
    name: str
    version: Optional[Version] = None
    ctan: Optional[_Ctan] = None
    install: Optional[str] = None
