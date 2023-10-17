from collections import defaultdict
from datetime import date
import io
import logging
import os
from os.path import abspath, basename, join
import re
import subprocess
import sys
import zipfile
from typing import TypedDict
from dateutil import parser

import requests
from app.helpers import helpers

from app.schemas import Package, Version

# TODO: Test these new Regexes
provides_pattern = r'\\Provides(?:Package|File|Class)\s*\{(?P<name>.*?)\}\s*(?:\[(?P<version>[\S\s]*?)\])?'
provides_expl_pattern = r'\\ProvidesExplPackage\s*\{(?P<name>.*?)\}\s*\{(?P<version>.*?\}\s*\{.*?)\}\s*\{(.*?)\}'


class VersionFromIndex(TypedDict):
    raw: str
    date: date
    number: str


def version_matches(version: VersionFromIndex, pkg_version: Version):
    # TODO: Is this enough?
    if type(version['date']) == str:
        version['date'] = parser.parse(version['date']).date()
    if type(pkg_version.date) == str:
        pkg_version.date = parser.parse(pkg_version.date).date()
        
    if not pkg_version:
        return True
    if pkg_version.date and pkg_version.date == version['date']:
        return True
    if pkg_version.number and pkg_version.number == version['number']:
        return True
    return False


def parse_version(version: str) -> VersionFromIndex:
    if version == "" or version == None:
        return {'raw': version, 'date': None, 'number': None}

    if(type(version) == str):  # e.g. '2005/05/09 v0.3 1, 2, many: numbersets  (ums)'
        # Assumes version number is followed by a space
        number_pattern = r"\d+\.\d+(?:\.\d+)?-?(?:[a-z0-9])*\b"
        single_number_pattern = r"(?<=v)\d" # Problem: Trying to capture single-digit versions without leading v would capture numbers in date

        number_match = re.search(number_pattern, version)
        single_number_match = re.search(single_number_pattern, version)

        if number_match:
            number = number_match.group()
        elif single_number_match:
            number = single_number_match.group()
        else:
            number = None

        date = None
        try:
            date = parser.parse(version, fuzzy=True).date()
        except parser.ParserError:
            try:
                date = parser.parse(version, fuzzy=True, dayfirst=True).date()
            except Exception as e:
                print(f"Cannot parse {version}: {e}")
                date = None

        return {'raw': version, 'date': date, 'number': number}

    raise TypeError(f"Cannot parse {version} of type {type(version)}")


def parse_changed_files(path_to_ctan: str) -> "list[str]":
    fpath = os.path.join(path_to_ctan, 'FILES.last07days')
    with open(fpath, 'r') as f:
        lines = f.readlines()
        files_changed = [line.split('|')[-1].strip() for line in lines]

    return [file for file in files_changed if not file.startswith(('systems', 'indexing', 'install'))]


def download_files_to_binary_zip(file_urls: "list[str]", pkg_id: str) -> bytes:
    zip_filename = "%s.zip" % pkg_id

    s = io.BytesIO()
    zf = zipfile.ZipFile(file=s, mode="w")

    for url in file_urls:
        # Calculate path for file in zip
        fname = os.path.basename(url).split('?')[0]
        if not fname:  # E.g. hyperref, which has /doc folder
            continue

        resp = requests.get(url)
        if not resp.ok:
            raise RuntimeError("Couldnt get file at " + url)

        # Add file, at correct path
        zf.writestr(data=resp.content, zinfo_or_arcname=fname)

    # Must close zip for all contents to be written
    zf.close()

    print("Successfully built zip-file, returning it now")

    # Grab ZIP file from in-memory, return
    return s.getvalue()


def install_file(file: str):
    path, fname = os.path.split(file)
    old_cwd = os.getcwd()
    os.chdir(abspath(path))

    try:
        if fname.endswith('.ins'):
            subprocess.run(['latex', fname], stdout=subprocess.DEVNULL, timeout=3)
        elif fname.endswith('.dtx'):
            subprocess.run(['tex',   fname], stdout=subprocess.DEVNULL, timeout=2)
        else:
            raise ValueError(f"{fname} is not an installable package-file")
    except:
        os.chdir(old_cwd)
        raise
    os.chdir(old_cwd)


def extract_version_from_file(fpath: str, pkg_id: str, index: defaultdict, commit_hash: str) -> bool:
    try:
        content, version_str = '', None
        # Read file
        try:
            with open(fpath, "r") as f:
                content = f.read()
        except Exception:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                # TODO: Find better solution, or figure out if this is good enough
                content = f.read()
                # print(f'Opened file {basename(fpath)} with errors="ignore" and encoding="utf-8". Error: {e}')
        
        for regex in [provides_pattern, provides_expl_pattern]:
            match = re.search(regex, content)
            if match:
                version_str = match.group('version') 
                
                # If version_str is a variable (e.g. \filedate), find definition of variable in sty-file and use that 
                for variable in re.findall(r'\\(?!n)[^\\]+', version_str):
                    pattern = r'\\def\s*%s\s*\{(.*?)\}' %re.escape(variable)
                    version_match = re.search(pattern, content)
                    if version_match:
                        version_str = version_str.replace(variable, " " + version_match.group(1) + " ")
                        logger.debug(f"Substituted {version_match.group(1)} for {variable} in {basename(fpath)}")
                break

        if not version_str:
            # Add to index even if no version found
            # Reason: Provides data for /search endpoint
            index[commit_hash][pkg_id][basename(fpath)] = None
            return False

        version = helpers.parse_version(version_str)

        index[commit_hash][pkg_id][basename(fpath)] = version
        print(f"{pkg_id}: {version_str}")
        return True

    except Exception as e:
        index[commit_hash][pkg_id]["Error"] = f"{basename(fpath)}: {e}"
        print(e)
        return False


def get_relevant_files(subdir: str, pkg: Package, sty_cls=True, ins=True, dtx=True):
    """Finds sty/cls that are named after pkg.id or pkg.name and all ins and dtx files"""
    relevant_files = {'sty/cls': [], 'ins': [], 'dtx': []}

    if subdir and os.path.islink(subdir):
        print(subdir + " is a symlink, resolving now")
        # TODO: Check if this works for e.g. a4 or other symlinked packages. See if os.walk finds the files
        subdir = os.readlink(subdir)
        print("subdir is now " + subdir)
    # Get relevant files in all subdirs. followlinks=True because for some packages, package folder is a symlink, e.g. a4
    for path, subdirs, files in os.walk(subdir, followlinks=True):
        for file in files:
            if sty_cls and file in [f"{pkg.name}.sty", f"{pkg.name}.cls", f"{pkg.id}.sty", f"{pkg.id}.cls"]:
                relevant_files['sty/cls'].append(join(path, file))
            elif ins and file.endswith('.ins'):
                relevant_files['ins'].insert(0 if basename(file).startswith(pkg.name) or basename(file).startswith(pkg.id) else -1, join(path, file))
            elif dtx and file.endswith('.dtx'):
                relevant_files['dtx'].insert(0 if basename(file).startswith(pkg.name) or basename(file).startswith(pkg.id) else -1, join(path, file))
    return relevant_files


def make_logger(name: str = "default"):
    logger = logging.getLogger(name)
    if logger.handlers:  # Logger already existed
        return logger

    logger.setLevel(logging.DEBUG)  # Set the desired log level
    logger.propagate = 0

    # Logging to stdout
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)

    # Logging to .log file
    log_file_name = f'log/{name}.log'
    os.makedirs(os.path.dirname(log_file_name), exist_ok=True)  # Make sure folder for log-file exists
    fh = logging.FileHandler(log_file_name)
    fh.setLevel(logging.DEBUG)

    # Custom format for logs
    format_string = '%(asctime)s - %(levelname)-8s - %(message)s'
    formatter = logging.Formatter(format_string, '%H:%M:%S')

    fh.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(fh)
    logger.addHandler(stream_handler)

    return logger


logger = make_logger()
