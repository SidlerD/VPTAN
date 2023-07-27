from datetime import date
import re
from typing import Optional, Union
from dateutil    import parser
import requests
from fastapi import HTTPException, status

from app.schemas import Package


async def pkg_id_exists(pkg_id: str) -> Package:
    """Returns Package object for pkg_id which are valid according to CTAN, i.e. querying https://www.ctan.org/json/2.0/pkg/{pkg_id} will be successful
    Note: Some packages have aliases. pkg_id must be the package that aliases the package whose files you want"""
    url = f"https://www.ctan.org/json/2.0/pkg/{pkg_id}"
    res = requests.get(url)
    if res.ok:
        data = res.json()
        if 'id' in data:
            return Package(**data)
    
    raise HTTPException(
        status_code= status.HTTP_404_NOT_FOUND, 
        detail={
            'message': f"{pkg_id} does not exist on CTAN. See 'url'", 
            'url': url
        }
    )

def valid_date(date: Union[str, None] = None) -> Optional[date]:
    if not date:
        return None
    try:
        # NOTE: This pattern is also used in backend: Changes need to be applied in both places
        date_pattern = r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}"
        date_match = re.search(date_pattern, date)
        if date_match:
            return parser.parse(date_match.group()).date()
    except:
        print('date not valid')
    
    raise HTTPException(status_code=400, detail=f"Cannot parse provided date: {date}")