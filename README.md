# VPTAN: Versioned Packages for Tex Archive Network
VPTAN provides an easy-to-use API to download packages in historic versions. It can be thought of as CTAN with version history for packages. It was initially developed as a backend for [lpm](https://github.com/SidlerD/latexPM), but can also be used on its own.

## Source repository
VPTAN doesn't host its own repository/archive that stores older versions of packages. Instead it is built on top of the existing [historical git archive of CTAN](https://git.texlive.info/CTAN/), which is hosted by texlive.info. Any call to VPTAN with a specified version will internally figure out under which commit-hash the package can be found in the right version and download the file from the afore-mentioned git archive.

## Setup
### Using Docker
We provide ready-to-use images of VPTAN on the [Docker Hub](https://hub.docker.com/repository/docker/sidlerd/vptan/general). If you already have Docker installed, this should be the easiest way of getting started with VPTAN.

1. Pull the image

   `docker pull sidlerd/vptan:<tag>`

   Note: A list of valid `<tags>` can be found at https://hub.docker.com/repository/docker/sidlerd/vptan/general under Tags

2. Run the container

   `docker run -p 8000:8000 sidlerd/vptan:<tag>`

   Run the container you just pulled. The option `-p 8000:8000` is needed so that you can access the API on your machine

3. Test the API

   Go to http://127.0.0.1:8000/ to see if the API is running. 

### Using git clone
If you don't want to run VPTAN using Docker, you can clone the repository to your machine and run it manually

1. Clone this repository

   `git clone https://github.com/SidlerD/VPTAN.git`

2. Go into VPTAN's directory

   `cd VPTAN`

3. [Start a virtual environment](https://python.land/virtual-environments/virtualenv) and install VPTAN's dependencies

    1. `python -m venv venv`
    2. `source venv/bin/activate`
    3. `pip install -r requirements.txt`

4. Start VPTAN

   `python -m app.main`

5. Test the API

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