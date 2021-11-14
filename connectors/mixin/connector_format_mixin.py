from abc import ABC
from typing import Optional, Union

try:  # Assume we're a sub-module in a package.
    from utils import arguments as arg
    from interfaces import (
        LeafConnectorInterface, StructInterface, StructFileInterface, IterableStreamInterface,
        ItemType, FieldType, DialectType, StreamType, ContentType,
        AUTO, Auto, AutoBool, Columns, Array, ARRAY_TYPES,
    )
    from items.struct_mixin import StructMixin
    from connectors.content_format.text_format import AbstractFormat, ParsedFormat, TextFormat
    from connectors.content_format.lean_format import LeanFormat, ColumnarFormat, FlatStructFormat
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...utils import arguments as arg
    from ...interfaces import (
        LeafConnectorInterface, StructInterface, StructFileInterface, IterableStreamInterface,
        ItemType, FieldType, DialectType, StreamType, ContentType,
        AUTO, Auto, AutoBool, Columns, Array, ARRAY_TYPES,
    )
    from ...items.struct_mixin import StructMixin
    from ..content_format.text_format import AbstractFormat, ParsedFormat, TextFormat
    from ..content_format.lean_format import LeanFormat, ColumnarFormat, FlatStructFormat

Native = Union[LeafConnectorInterface, IterableStreamInterface, StructFileInterface]
Struct = Optional[StructInterface]


class ConnectorFormatMixin(LeafConnectorInterface, StructMixin, ABC):
    def get_initial_struct(self) -> Struct:
        initial_format = self.get_declared_format()
        if isinstance(initial_format, FlatStructFormat) or hasattr(initial_format, 'get_struct'):
            return initial_format.get_struct()

    def set_initial_struct(self, struct: Struct, inplace: bool) -> Optional[Native]:
        struct = self._get_native_struct(struct).copy()
        initial_format = self.get_declared_format()
        if inplace:
            if isinstance(initial_format, (LeanFormat, ColumnarFormat)) or hasattr(initial_format, 'set_struct'):
                initial_format.set_struct(struct, inplace=True)
            else:
                raise TypeError('Cannot set struct for {}: method not supported (by design)'.format(initial_format))
        else:
            copy = self.make_new()
            assert isinstance(copy, ConnectorFormatMixin)
            copy.set_initial_struct(struct, inplace=True)
            return self._assume_native(copy)

    def initial_struct(self, struct: Struct) -> Native:
        struct = self._get_native_struct(struct).copy()
        self.set_initial_struct(struct, inplace=True)
        return self._assume_native(self)

    def get_struct(self) -> Struct:
        content_format = self.get_content_format()
        if isinstance(content_format, FlatStructFormat) or hasattr(content_format, 'get_struct'):
            struct = content_format.get_struct()
        else:
            struct = None
        return self._get_native_struct(struct)

    def set_struct(self, struct: Struct, inplace: bool) -> Optional[Native]:
        struct = self._get_native_struct(struct, verbose=False)
        content_format = self.get_content_format()
        if inplace:
            if isinstance(content_format, (LeanFormat, ColumnarFormat)) or hasattr(content_format, 'set_struct'):
                content_format.set_struct(struct, inplace=True)
            else:
                raise TypeError('Cannot set struct for {}: method not supported (by design)'.format(content_format))
            if not self.get_initial_struct():
                self.set_initial_struct(struct, inplace=True)
        else:
            # return self.make_new(struct=struct)
            copy = self.make_new()
            assert isinstance(copy, ConnectorFormatMixin)
            copy.set_struct(struct, inplace=True)
            return self._assume_native(copy)

    def struct(self, struct: Struct) -> Native:
        struct = self._get_native_struct(struct).copy()
        self.set_struct(struct, inplace=True)
        return self._assume_native(self)

    def reset_struct_to_initial(self, verbose: bool = True, message: Optional[str] = None) -> Native:
        if not arg.is_defined(message):
            message = self.__repr__()
        if verbose:
            for line in self.get_struct().get_struct_comparison_iter(self.get_initial_struct(), message=message):
                self.log(line)
        return self.struct(self.get_initial_struct())

    def get_delimiter(self) -> str:
        content_format = self.get_content_format()
        if isinstance(content_format, ColumnarFormat) or hasattr(content_format, 'get_delimiter'):
            return content_format.get_delimiter()
        else:
            example_line = self.get_first_line() if self.is_existing() else ''
            return ColumnarFormat.detect_delimiter_by_example_line(example_line)

    def set_delimiter(self, delimiter: str, inplace: bool) -> Optional[Native]:
        content_format = self.get_content_format()
        if isinstance(content_format, ColumnarFormat) or hasattr(content_format, 'set_delimiter'):
            content_format = content_format.set_delimiter(delimiter, inplace=inplace)
            if not inplace:
                return self.set_content_format(content_format, inplace=inplace)
        elif isinstance(content_format, TextFormat):
            content_format = ColumnarFormat(delimiter=delimiter, **content_format.get_props())
            return self.set_content_format(content_format, inplace=inplace)

    def is_first_line_title(self) -> bool:
        content_format = self.get_content_format()
        if isinstance(content_format, ColumnarFormat) or hasattr(content_format, 'is_first_line_title'):
            return content_format.is_first_line_title()
        else:
            return False

    def get_title_row(self, close: bool = True) -> tuple:
        assert self.is_first_line_title(), 'For receive title row file/object must have first_line_is_title-flag'
        first_line = self.get_first_line(close=close)
        content_format = self.get_content_format()
        if isinstance(content_format, ColumnarFormat):
            title_row = content_format.get_parsed_line(first_line, item_type=ItemType.Row)
        else:
            delimiter = ColumnarFormat.detect_delimiter_by_example_line(first_line)
            title_row = ColumnarFormat(False, delimiter).get_parsed_line(first_line, item_type=ItemType.Row)
        return title_row

    def get_detected_struct_by_title_row(self, set_struct: bool = False, verbose: AutoBool = AUTO) -> Struct:
        assert self.is_first_line_title(), 'Can detect struct by title row only if first line is a title row'
        assert self.is_existing(), 'For detect struct by title row file/object must be existing'
        verbose = arg.acquire(verbose, self.is_verbose())
        title_row = self.get_title_row(close=True)
        struct = self._get_struct_detected_by_title_row(title_row)
        message = 'Struct for {} detected by title row: {}'.format(self.get_name(), struct.get_struct_str(None))
        self.log(message, end='\n', verbose=verbose)
        if set_struct:
            self.set_struct(struct, inplace=True)
        return struct

    def is_gzip(self) -> bool:
        content_format = self.get_content_format()
        if isinstance(content_format, ParsedFormat):
            return content_format.is_gzip()
        return False

    def get_stream_type(self) -> StreamType:
        content_format = self.get_content_format()
        return content_format.get_default_stream_type()

    def get_item_type(self) -> ItemType:
        stream_class = self.get_stream_type().get_class()
        if hasattr(stream_class, 'get_item_type'):
            return stream_class.get_item_type()
        else:
            stream_obj = stream_class([])
        if hasattr(stream_obj, 'get_item_type'):
            return stream_obj.get_item_type()
        else:
            return ItemType.Any

    def get_content_type(self) -> ContentType:
        return self.get_content_format().get_content_type()

    @staticmethod
    def _assume_native(connector) -> Native:
        return connector
