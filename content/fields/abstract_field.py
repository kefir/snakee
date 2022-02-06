from abc import ABC
from typing import Optional, Callable, Union

try:  # Assume we're a submodule in a package.
    from base.classes.auto import Auto, AUTO
    from base.functions.arguments import get_name, get_value
    from base.abstract.simple_data import SimpleDataWrapper
    from interfaces import FieldInterface, StructInterface, FieldType, DialectType, ARRAY_TYPES
    from content.struct import flat_struct as fc
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...base.classes.auto import Auto, AUTO
    from ...base.functions.arguments import get_name, get_value
    from ...base.abstract.simple_data import SimpleDataWrapper
    from ...interfaces import FieldInterface, StructInterface, FieldType, DialectType, ARRAY_TYPES
    from ..struct import flat_struct as fc


class AbstractField(SimpleDataWrapper, FieldInterface, ABC):
    def __init__(self, name: str, field_type: FieldType = FieldType.Any, properties=None):
        field_type = Auto.delayed_acquire(field_type, FieldType.detect_by_name, field_name=name)
        field_type = FieldType.get_canonic_type(field_type, ignore_missing=True)
        assert isinstance(field_type, FieldType), 'Expected FieldType, got {}'.format(field_type)
        self._type = field_type
        super().__init__(name=name, data=properties)

    def set_type(self, field_type: FieldType, inplace: bool) -> Optional[FieldInterface]:
        if inplace:
            self._type = field_type
        else:
            return self.set_outplace(field_type=field_type)

    def get_type(self) -> FieldType:
        return self._type

    def get_type_name(self) -> str:
        type_name = get_value(self.get_type())
        if not isinstance(type_name, str):
            type_name = get_name(type_name)
        return str(type_name)

    def get_type_in(self, dialect: DialectType):
        if not isinstance(dialect, DialectType):
            dialect = DialectType.detect(dialect)
        if dialect == DialectType.String:
            return self.get_type_name()
        else:
            return self.get_type().get_type_in(dialect)

    def get_converter(self, source: DialectType, target: DialectType) -> Callable:
        return self.get_type().get_converter(source, target)

    def __repr__(self):
        return '{}: {}'.format(self.get_name(), self.get_type_name())

    def __str__(self):
        return self.get_name()

    def __add__(self, other: Union[FieldInterface, StructInterface, str]) -> StructInterface:
        if isinstance(other, str):
            return fc.FlatStruct([self, self.__class__(other)])
        elif isinstance(other, AbstractField):
            return fc.FlatStruct([self, other])
        elif isinstance(other, ARRAY_TYPES):
            return fc.FlatStruct([self] + list(other))
        elif isinstance(other, StructInterface):
            struct = other.append_field(self, before=True, inplace=False)
            assert isinstance(struct, StructInterface), struct
            return struct
        else:
            raise TypeError('Expected other as field or struct, got {} as {}'.format(other, type(other)))
