from abc import ABC, abstractmethod, abstractproperty

from app.schemas import Package

class IArchive(ABC):
    
    @abstractmethod
    def update_index(self):
        pass

    @abstractmethod
    def get_pkg_files(self, pkg: Package):
        pass

