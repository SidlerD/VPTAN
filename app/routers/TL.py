import io
import logging

from datetime import date
import os
from os.path import join
from urllib.parse import urljoin
import zipfile
from fastapi import HTTPException, Response, status
import requests
from bs4 import BeautifulSoup as bs4

from app.schemas import Package, Version

logger = logging.getLogger("default")

def download_pkg(pkg: Package, version: Version):
    print(f"TL: Downloading {pkg.id} {version}")
    """
        let elems = document.querySelectorAll("div.content td > a.ls-blob")
        let links = Array.from(elems).map(elem => elem.getAttribute("href"))
    """
    if not pkg.ctan and pkg.ctan.path:
        raise NotImplementedError("Can only download packages where I know the ctan path")
    
    base_url = "https://git.texlive.info/CTAN/plain"
    url = base_url + pkg.ctan.path
    page = requests.get(url)  

    soup = bs4(page.content, "html.parser")

    a_tags = soup.select("ul a")
    urls = [urljoin(base_url, elem['href']) for elem in a_tags if elem.text != "../"]

    print(urls)

    return write_files_to_binary_zip(urls, pkg.id)


def write_files_to_binary_zip(file_urls: list[str], pkg_id: str):
    zip_filename = "%s.zip" % pkg_id

    s = io.BytesIO()
    zf = zipfile.ZipFile(file=s, mode="w")

    for url in file_urls:
        # Calculate path for file in zip
        fname = os.path.basename(url)
        if not fname: # E.g. hyperref, which has /doc folder
            continue

        resp = requests.get(url)
        if not resp.ok:
            raise RuntimeError("Couldnt get file at " + url)
        
        # Add file, at correct path
        zf.writestr(data=resp.content, zinfo_or_arcname = fname)

    # Must close zip for all contents to be written
    zf.close()

    # Grab ZIP file from in-memory, make response with correct MIME-type
    resp = Response(s.getvalue(), media_type="application/x-zip-compressed", headers={
        'Content-Disposition': f'attachment;filename={zip_filename}'
    })

    return resp