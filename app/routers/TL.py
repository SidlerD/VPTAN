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
from app.routers import History

from app.schemas import Package, Version

logger = logging.getLogger("default")

def download_pkg(pkg: Package, version: Version) -> bytes:
    """
        let elems = document.querySelectorAll("div.content td > a.ls-blob")
        let links = Array.from(elems).map(elem => elem.getAttribute("href"))
    """
    if not pkg.ctan and pkg.ctan.path:
        raise NotImplementedError("Can only download packages where I know the ctan path")
    
    base_url = "https://git.texlive.info/CTAN/plain"
    commit_hash = History.get_commit_hash(pkg, version)
    overview_url =f"{base_url}{pkg.ctan.path}?id={commit_hash}"

    page = requests.get(overview_url)  
    soup = bs4(page.content, "html.parser")

    a_tags = soup.select("ul a")
    urls = [urljoin(base_url, elem['href']) for elem in a_tags if elem.text != "../"]

    logger.info(f"Downloading {len(urls)} files from {overview_url}")

    return write_files_to_binary_zip(urls, pkg.id)


def write_files_to_binary_zip(file_urls: list[str], pkg_id: str) -> bytes:
    zip_filename = "%s.zip" % pkg_id

    s = io.BytesIO()
    zf = zipfile.ZipFile(file=s, mode="w")

    for url in file_urls:
        # Calculate path for file in zip
        fname = os.path.basename(url).split('?')[0]
        if not fname: # E.g. hyperref, which has /doc folder
            continue

        resp = requests.get(url)
        if not resp.ok:
            raise RuntimeError("Couldnt get file at " + url)
        
        # Add file, at correct path
        zf.writestr(data=resp.content, zinfo_or_arcname = fname)

    # Must close zip for all contents to be written
    zf.close()

    logger.info(f"Successfully built zip-file, returning it now")

    # Grab ZIP file from in-memory, return
    return s.getvalue()