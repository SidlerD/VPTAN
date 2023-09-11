import datetime as dt
from typing import Optional, Union
# from pydantic import BaseModel, model_validator, root_validator
import pydantic
from dateutil import parser
    
    # @model_validator(mode='before')
    # def parse_date(cls, data):
    #     if data['date'] == "" or data['date'] == None:
    #         data['date'] == None
    #     elif 'date' in data and data['date'] and type(data['date']) == str:
    #         data['date'] = parser.parse(data['date'])
    #     else:
    #         raise ValueError("Cannot parse version.date: " + data['date'])
        
    #     return data

    # @model_validator(mode='after')
    # def check_date_format(self) -> 'Version':
    #     if self.date and not isinstance(self.date, dt.date):
    #         self.date = parser.parse(self.date)
    #         return self
    #     raise ValueError('Version.date needs to be of type datetime.date')

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
