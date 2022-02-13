from abc import ABC
from typing import Union, Optional, Iterable, Generator

try:  # Assume we're a submodule in a package.
    from base.classes.auto import Auto, AUTO
    from base.functions.arguments import get_list
    from base.interfaces.base_interface import BaseInterface
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ..classes.auto import Auto, AUTO
    from ..functions.arguments import get_list
    from ..interfaces.base_interface import BaseInterface

Native = BaseInterface
OptionalFields = Optional[Union[str, Iterable]]


class AbstractBaseObject(BaseInterface, ABC):
    def set_inplace(self, **kwargs) -> Native:
        for k, v in kwargs.items():
            try:
                method_name = 'set_{}'.format(k)
                method = self.__getattribute__(method_name)
                method(v)
            except AttributeError:
                self.__dict__[k] = v
        return self

    def set_outplace(self, **kwargs) -> Native:
        props = self.get_props()
        props.update(kwargs)
        if 'check' in props:
            props['check'] = False
        return self.__class__(**props)

    @classmethod
    def _get_meta_member_mapping(cls) -> dict:
        return dict()

    @classmethod
    def _get_key_member_names(cls):
        return list()

    def get_key_member_values(self) -> list:
        key_meta = list()
        for field in self._get_key_member_names():
            value = self.__dict__.get(field)
            if hasattr(value, 'get_name'):
                key_meta.append(value.get_name())
            else:
                key_meta.append(str(value))
        return key_meta

    @classmethod
    def _get_meta_field_by_member_name(cls, name: str) -> str:
        name = cls._get_meta_member_mapping().get(name, name)
        if name.startswith('_'):
            name = name[1:]
        return name

    @classmethod
    def _get_data_member_names(cls) -> tuple:
        return tuple()

    @classmethod
    def _get_data_fields_list(cls) -> list:
        return [cls._get_meta_field_by_member_name(m) for m in cls._get_data_member_names()]

    def _get_data_member_items(self) -> Iterable:
        for k in self._get_data_member_names():
            yield self.__dict__[k]

    @classmethod
    def _get_meta_member_names(cls) -> list:
        return list()

    @classmethod
    def get_meta_fields_list(cls) -> list:
        return [cls._get_meta_field_by_member_name(k) for k in cls._get_meta_member_names()]

    @staticmethod
    def _get_other_meta_fields_list(other: Union[Native, Auto] = AUTO) -> tuple:
        if other == AUTO:
            return tuple()
        elif hasattr(other, 'get_meta_fields_list'):
            other_meta = other.get_meta_fields_list()
        elif hasattr(other, 'get_meta'):
            other_meta = other.get_meta()
        else:
            other_meta = tuple()
        return other_meta

    def _meta_member_items(self) -> Generator:
        for k in self._get_meta_member_names():
            yield k, self.__dict__[k]

    def get_props(self, ex: OptionalFields = None, check: bool = True) -> dict:
        props = dict()
        ex_list = get_list(ex)
        for k, v in self.__dict__.items():
            k = self._get_meta_field_by_member_name(k)
            if k in ex_list:
                ex_list.remove(k)
            else:
                props[k] = v
        if check:
            assert not ex_list, 'get_props() got unexpected fields: {}'.format(ex_list)
        return props

    def get_meta(self, ex: OptionalFields = None) -> dict:
        ex_list = get_list(ex)
        ex_list += self._get_data_fields_list()
        meta = self.get_props(ex=ex_list)
        return meta

    def set_meta(self, inplace: bool = False, **meta) -> Native:
        if inplace:
            current_meta = self.get_meta()
            current_meta.update(meta)
            return self.set_inplace(**current_meta) or self
        else:
            return self.__class__(*self._get_data_member_items(), **meta)

    def update_meta(self, inplace: bool = False, **meta) -> Native:
        current_meta = self.get_meta()
        current_meta.update(meta)
        if inplace:
            return self.set_inplace(**current_meta) or self
        else:
            return self.__class__(*self._get_data_member_items(), **current_meta)

    def fill_meta(self, check: bool = True, **meta) -> Native:
        old_meta = self.get_meta()
        new_meta = meta.copy()
        new_meta.update(old_meta)
        if check:
            unsupported = [k for k in meta if k not in old_meta]
            assert not unsupported, 'class {} does not support these properties: {}'.format(
                self.__class__.__name__,
                unsupported,
            )
        for key, value in new_meta.items():
            if value is None or value == AUTO:
                new_meta[key] = old_meta.get(key)
        return self.__class__(*self._get_data_member_items(), **new_meta)

    def get_compatible_meta(self, other=AUTO, ex=None, **kwargs) -> dict:
        other_meta = self._get_other_meta_fields_list(other)
        compatible_meta = dict()
        for k, v in list(self.get_meta(ex=ex).items()) + list(kwargs.items()):
            if k in other_meta:
                compatible_meta[k] = v
        return compatible_meta

    @staticmethod
    def _get_covert_props() -> tuple:
        return tuple()

    def _get_meta_args(self) -> list:
        return [self.__dict__[k] for k in self._get_key_member_names()]

    def _get_meta_kwargs(self, except_covert: bool = False) -> dict:
        meta_kwargs = self.get_meta().copy()
        for f in self._get_key_member_names():
            meta_kwargs.pop(self._get_meta_field_by_member_name(f), None)
        if except_covert:
            for f in self._get_covert_props():
                meta_kwargs[f] = '***'
        return meta_kwargs

    def get_str_meta(self) -> str:
        args_str = [i.__repr__() for i in self._get_meta_args()]
        kwargs_str = ['{}={}'.format(k, v) for k, v in self._get_meta_kwargs(except_covert=True).items()]
        return ', '.join(args_str + kwargs_str)

    def get_detailed_repr(self) -> str:
        return '{}({})'.format(self.__class__.__name__, self.get_str_meta())

    def make_new(self, *args, ex: OptionalFields = None, **kwargs):
        meta = self.get_meta(ex=ex)
        meta.update(kwargs)
        return self.__class__(*args, **meta)

    def __eq__(self, other):
        if hasattr(other, 'get_key_member_values'):
            return self.get_key_member_values() == other.get_key_member_values()

    def __repr__(self):
        return self.get_detailed_repr()

    def __str__(self):
        return '<{}>'.format(self.get_detailed_repr())
