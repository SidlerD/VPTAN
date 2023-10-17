# VPTAN: Versioned Packages for Tex Archive Network
VPTAN provides an easy-to-use API to download packages in historic versions. It can be thought of as CTAN with version history for packages. It was initially developed as a backend for [lpm](https://github.com/SidlerD/latexPM), but can also be used on its own.

## Source repository
VPTAN doesn't host its own repository/archive that stores older versions of packages. Instead it is built on top of the existing [historical git archive of CTAN](https://git.texlive.info/CTAN/), which is hosted by texlive.info. Any call to VPTAN with a specified version will internally figure out under which commit-hash the package can be found in the right version and download the file from the afore-mentioned git archive.

## Setup

1. Clone this repository

   `git clone https://github.com/SidlerD/VPTAN.git`

2. Go into VPTAN's directory

   `cd VPTAN`

3. [Create and start a virtual environment](https://python.land/virtual-environments/virtualenv) with the name venv (Note: Use python 3.10.2 when creating venv)

4. Install VPTAN's dependencies

   `pip install -r requirements.txt`

5. Start VPTAN

   `python -m app.main`

6. Test the API

   Go to http://127.0.0.1:8000/ to see if the API is running. 

## Documentation
We will only provide a short overview of the API here. To see the full documentation, run VPTAN and go to [/docs](http://127.0.0.1:8000/docs)

### /packages/{pkg_id}
#### Required
- *pkg_id*: Id of the package you want to download, e.g. "amsmath"

#### Optional
- *number*: Version number to download, e.g. 2.17j
- *date*: Version date to download, e.g. 2021-04-20
- *closest*: If requested version is not available, should the closest later version be downloaded?

### /alias

Some packages on CTAN are available under an alias, e.g. pgf which has the alias tikz. This endpoint can be used to get the name of the original package based on its alias

#### Optional
- *id*: Id of the package you want to know the alias of, e.g. tikz
- *name*: Name of the package you want to know the alias of, e.g. TikZ (providing only id is preferable)
