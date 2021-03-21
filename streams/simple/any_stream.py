from typing import Union, Iterable, Optional
from inspect import isclass

try:  # Assume we're a sub-module in a package.
    from streams import stream_classes as sm
    from utils import (
        arguments as arg,
        items as it,
        selection as sf,
    )
    from selection import selection_classes as sn
    # from loggers.logger_classes import deprecated_with_alternative
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from .. import stream_classes as sm
    from ...utils import (
        arguments as arg,
        items as it,
        selection as sf,
    )
    from ...selection import selection_classes as sn
    # from ...loggers.logger_classes import deprecated_with_alternative

OptionalFields = Optional[Union[str, Iterable]]
Stream = Union[sm.LocalStream, sm.ColumnarMixin, sm.ConvertMixin]


class AnyStream(sm.LocalStream, sm.ConvertMixin):
    def __init__(
            self,
            data,
            name=arg.DEFAULT,
            count=None, less_than=None,
            source=None, context=None,
            check=False,
            max_items_in_memory=arg.DEFAULT,
            tmp_files_template=arg.DEFAULT,
            tmp_files_encoding=arg.DEFAULT,
    ):
        super().__init__(
            data,
            name=name, check=check,
            count=count, less_than=less_than,
            source=source, context=context,
            max_items_in_memory=max_items_in_memory,
            tmp_files_template=tmp_files_template,
            tmp_files_encoding=tmp_files_encoding,
        )

    @staticmethod
    def get_item_type() -> it.ItemType:
        return it.ItemType.Any

    def filter(self, *functions) -> Stream:
        def filter_function(item):
            for f in functions:
                if not f(item):
                    return False
            return True
        stream = super().filter(filter_function)
        return self._assume_native(stream)

    def select(self, *columns, use_extended_method=True, **expressions) -> Stream:
        if columns and not expressions:
            target_stream_type = sm.StreamType.RowStream
            target_item_type = it.ItemType.Row
            input_item_type = it.ItemType.Any
        elif expressions and not columns:
            target_stream_type = sm.StreamType.RecordStream
            target_item_type = it.ItemType.Record
            input_item_type = it.ItemType.Any
        else:
            target_stream_type = sm.StreamType.AnyStream
            target_item_type = it.ItemType.Auto
            input_item_type = it.ItemType.Auto
        if use_extended_method:
            selection_method = sn.select
        else:
            selection_method = sf.select
        select_function = selection_method(
            *columns, **expressions,
            target_item_type=target_item_type, input_item_type=input_item_type,
            logger=self.get_logger(), selection_logger=self.get_selection_logger(),
        )
        return self.map(
            function=select_function,
            to=target_stream_type,
        )

    def map(self, function, to=arg.DEFAULT) -> Stream:
        stream = super().map(function, to=to)
        return self._assume_native(stream)

    def flat_map(self, function, to=arg.DEFAULT) -> Stream:
        def get_items():
            for i in self.get_iter():
                yield from function(i)
        to = arg.undefault(to, self.get_stream_type())
        stream_class = sm.get_class(to)
        new_props_keys = stream_class([]).get_meta().keys()
        props = {k: v for k, v in self.get_meta().items() if k in new_props_keys}
        props.pop('count')
        return stream_class(
            get_items(),
            **props
        )

    # @deprecated_with_alternative('map()')
    def native_map(self, function) -> Stream:
        return self.stream(
            map(function, self.get_items()),
        )

    def apply_to_data(self, function, save_count=False, lazy=True, stream_type=arg.DEFAULT, *args, **kwargs) -> Stream:
        upd_meta = dict(count=self.get_count()) if save_count else dict()
        return self.stream(
            self.lazy_calc(function, *args, **kwargs) if lazy else self.calc(function, *args, **kwargs),
            stream_type=stream_type,
            **upd_meta
        )

    @staticmethod
    def _assume_native(stream) -> Stream:
        return stream

    def stream(self, data: Iterable, ex: OptionalFields = None, **kwargs) -> Stream:
        stream = self.to_stream(data, ex=ex, **kwargs)
        return self._assume_native(stream)

    def to_stream(
            self,
            data: Union[Iterable, arg.DefaultArgument] = arg.DEFAULT,
            stream_type=arg.DEFAULT,
            ex: OptionalFields = None,
            **kwargs
    ) -> Stream:
        stream_type = arg.undefault(stream_type, self.get_stream_type())
        if data == arg.DEFAULT:
            data = self.get_data()
        if isinstance(stream_type, str):
            stream_class = sm.StreamType(stream_type).get_class()
        elif isclass(stream_type):
            stream_class = stream_type
        else:
            stream_class = stream_type.get_class()
        meta = self.get_compatible_meta(stream_class, ex=ex)
        meta.update(kwargs)
        if 'count' not in meta:
            meta['count'] = self.get_count()
        if 'source' not in meta:
            meta['source'] = self.get_source()
        stream = stream_class(data, **meta)
        return self._assume_native(stream)

    @classmethod
    # @deprecated_with_alternative('connectors.filesystem.local_file.JsonFile.to_stream()')
    def from_json_file(
            cls,
            filename,
            encoding=None, gzip=False,
            skip_first_line=False, max_count=None,
            check=arg.DEFAULT,
            verbose=False,
    ) -> Stream:
        return sm.LineStream.from_text_file(
            filename,
            encoding=encoding, gzip=gzip,
            skip_first_line=skip_first_line, max_count=max_count,
            check=check,
            verbose=verbose,
        ).parse_json(
            to=cls.__name__,
        )
