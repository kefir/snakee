from abc import ABC, abstractmethod
from typing import Optional, Iterable, Generator, Union

try:  # Assume we're a submodule in a package.
    from base.classes.auto import AUTO, Auto
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ..classes.auto import AUTO, Auto

OptionalFields = Union[str, Iterable, None]


class BaseInterface(ABC):
    @abstractmethod
    def set_inplace(self, **kwargs):
        pass

    @abstractmethod
    def set_outplace(self, **kwargs):
        pass

    @abstractmethod
    def get_key_member_values(self) -> list:
        pass

    @classmethod
    @abstractmethod
    def get_meta_fields_list(cls) -> list:
        pass

    @abstractmethod
    def get_props(self, ex: OptionalFields = None, check: bool = True) -> dict:
        pass

    @abstractmethod
    def get_meta(self, ex: OptionalFields = None) -> dict:
        pass

    @abstractmethod
    def set_meta(self, inplace: bool = False, **meta):
        pass

    @abstractmethod
    def update_meta(self, **meta):
        pass

    @abstractmethod
    def fill_meta(self, check: bool = True, **meta):
        pass

    @abstractmethod
    def get_compatible_meta(self, other=AUTO, ex: Optional[Iterable] = None, **kwargs) -> dict:
        pass

    @abstractmethod
    def get_ordered_meta_names(self, meta: Union[dict, Auto] = AUTO) -> Generator:
        pass

    @abstractmethod
    def get_meta_items(self, meta: Union[dict, Auto] = AUTO) -> Generator:
        pass

    @abstractmethod
    def get_str_meta(self) -> str:
        pass

    @abstractmethod
    def get_detailed_repr(self) -> str:
        pass

    @abstractmethod
    def make_new(self, *args, ex: OptionalFields = None, **kwargs):
        pass
