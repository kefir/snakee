from abc import ABC
from typing import Union, Iterable, Generator, Callable, Optional

try:  # Assume we're a submodule in a package.
    from interfaces import (
        Context, LoggerInterface, SelectionLogger, ExtLogger,
        Stream, RegularStream, RegularStreamInterface, StructStream, StructInterface, ColumnarInterface,
        StreamType, ItemType, JoinType, How,
        Count, UniKey, Item, Array, Columns, OptionalFields,
        AUTO, Auto, AutoBool,
    )
    from utils import algo, arguments as arg
    from utils.external import pd, DataFrame, get_use_objects_for_output
    from content.fields import field_classes as fc
    from base.abstract.contextual_data import ContextualDataWrapper
    from base.mixin.iterable_mixin import IterableMixin
    from functions.secondary import item_functions as fs
    from utils import selection as sf
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...interfaces import (
        Context, LoggerInterface, SelectionLogger, ExtLogger,
        Stream, RegularStream, RegularStreamInterface, StructStream, StructInterface, ColumnarInterface,
        StreamType, ItemType, JoinType, How,
        Count, UniKey, Item, Array, Columns, OptionalFields,
        AUTO, Auto, AutoBool,
    )
    from ...utils import algo, arguments as arg
    from ...utils.external import pd, DataFrame, get_use_objects_for_output
    from ...content.fields import field_classes as fc
    from ...base.abstract.contextual_data import ContextualDataWrapper
    from ...base.mixin.iterable_mixin import IterableMixin
    from ...functions.secondary import item_functions as fs
    from ...utils import selection as sf

Native = Union[RegularStreamInterface, ColumnarInterface]
Struct = Optional[StructInterface]

SAFE_COUNT_ITEMS_IN_MEMORY = 10000
EXAMPLE_STR_LEN = 12
DEFAULT_SHOW_COUNT = 10
DEFAULT_DETECT_COUNT = 100
LOGGING_LEVEL_INFO = 20


class ColumnarMixin(ContextualDataWrapper, IterableMixin, ColumnarInterface, ABC):
    @classmethod
    def is_valid_item(cls, item: Item) -> bool:
        return cls.get_item_type().isinstance(item)

    @classmethod
    def get_validated(cls, items: Iterable, skip_errors: bool = False, context: Context = None) -> Generator:
        for i in items:
            if cls.is_valid_item(i):
                yield i
            else:
                message = 'get_validated(): item {} is not a {}'.format(i, cls.get_item_type())
                if skip_errors:
                    if context:
                        context.get_logger().log(message)
                else:
                    raise TypeError(message)

    def validated(self, skip_errors: bool = False) -> Native:
        stream = self.stream(
            self.get_validated(self.get_items(), skip_errors=skip_errors),
        )
        return self._assume_native(stream)

    def get_shape(self) -> tuple:
        return self.get_count(), self.get_column_count()

    def get_description(self) -> str:
        return '{} rows, {} columns: {}'.format(
            self.get_str_count(),
            self.get_column_count(),
            ', '.join(self.get_columns()),
        )

    def get_column_count(self) -> int:
        return len(list(self.get_columns()))

    def select(self, *args, **kwargs) -> Stream:
        stream = self.to_stream()
        assert isinstance(stream, RegularStreamInterface) or hasattr(stream, 'select')
        stream = stream.select(*args, **kwargs)
        return self._assume_native(stream)

    def _get_filtered_items(
            self,
            *args,
            item_type: ItemType = ItemType.Auto,
            skip_errors: bool = False,
            logger: Union[LoggerInterface, Auto] = AUTO,
            **kwargs
    ) -> Iterable:
        logger = arg.delayed_acquire(logger, self.get_logger)
        item_type = arg.delayed_acquire(item_type, self.get_item_type)
        filter_function = sf.filter_items(
            *args, item_type=item_type,
            skip_errors=skip_errors, logger=logger,
            **kwargs,
        )
        return filter(filter_function, self.get_items())

    def filter(self, *args, item_type: ItemType = ItemType.Auto, skip_errors: bool = False, **kwargs) -> Native:
        item_type = arg.delayed_acquire(item_type, self.get_item_type)
        stream_type = self.get_stream_type()
        assert isinstance(stream_type, StreamType), 'Expected StreamType, got {}'.format(stream_type)
        filtered_items = self._get_filtered_items(*args, item_type=item_type, skip_errors=skip_errors, **kwargs)
        stream = self.to_stream(data=filtered_items, stream_type=stream_type)
        return self._assume_native(stream)

    def _get_flat_mapped_items(self, function: Callable) -> Generator:
        for i in self.get_items():
            yield from function(i)

    def flat_map(self, function: Callable, inplace: bool = False) -> Optional[Native]:
        items = self._get_flat_mapped_items(function=function)
        return self.set_items(items, inplace=inplace)

    def map_to(self, function: Callable, stream_type: StreamType) -> Stream:
        items = map(function, self.get_items())
        stream = self.stream(items, stream_type=stream_type)
        return self._assume_native(stream)

    def map(self, function: Callable) -> Native:
        stream = self.stream(
            map(function, self.get_items()),
        )
        return self._assume_native(stream)

    def map_side_join(
            self,
            right: Native,
            key: UniKey,
            how: How = JoinType.Left,
            right_is_uniq: bool = True,
            inplace: bool = False,
    ) -> Optional[Native]:
        key = arg.get_names(key)
        keys = arg.update([key])
        if not isinstance(how, JoinType):
            how = JoinType(how)
        joined_items = algo.map_side_join(
            iter_left=self.get_items(),
            iter_right=right.get_items(),
            key_function=fs.composite_key(keys),
            merge_function=fs.merge_two_items(),
            dict_function=fs.items_to_dict(),
            how=how,
            uniq_right=right_is_uniq,
        )
        if self.is_in_memory():
            joined_items = list(joined_items)
        if inplace:
            self.set_items(joined_items, count=self.get_count(), inplace=True)
        else:
            stream = self.stream(joined_items)
            meta = self.get_compatible_static_meta()
            stream = stream.set_meta(**meta)
            return self._assume_native(stream)

    def sorted_group_by(self, *keys, **kwargs) -> Stream:
        stream = self.to_stream()
        return self._assume_native(stream).sorted_group_by(*keys, **kwargs)

    def group_by(self, *keys, values: Optional[Iterable] = None, as_pairs: bool = False) -> Stream:
        keys = arg.get_names(keys)
        keys = arg.update(keys)
        values = arg.get_names(values)
        return self.sort(*keys).sorted_group_by(*keys, values=values, as_pairs=as_pairs)

    def apply_to_stream(self, function: Callable, *args, **kwargs) -> Stream:
        return function(self, *args, **kwargs)

    def get_selection_logger(self) -> SelectionLogger:
        if isinstance(self, ContextualDataWrapper) or hasattr(self, 'get_context'):
            context = self.get_context()
        else:
            context = None
        if context:
            return context.get_selection_logger()
        else:
            logger = self.get_logger()
            if isinstance(logger, ExtLogger) or hasattr(logger, 'get_selection_logger'):
                return logger.get_selection_logger()

    @staticmethod
    def _assume_native(stream) -> Native:
        return stream

    def update_count(self) -> Native:
        assert self.is_in_memory()
        count = len(self.get_list())
        self.set_expected_count(count)
        self.set_estimated_count(count)
        return self

    def actualize(self, force: bool = False) -> Native:
        source = self.get_source()
        if hasattr(source, 'actualize'):
            if hasattr(source, 'is_actual') and not force:
                if not source.is_actual():
                    source.actualize()
            else:
                source.actualize()
        if self.get_count():
            if self.get_count() < SAFE_COUNT_ITEMS_IN_MEMORY:
                if hasattr(self, '_collect_inplace'):
                    self._collect_inplace()
                    self.update_count()
        return self

    def structure(
            self,
            struct: StructInterface,
            skip_bad_rows: bool = False,
            skip_bad_values: bool = False,
            verbose: bool = True,
    ) -> StructStream:
        if hasattr(self, 'to_row_stream'):
            row_stream = self.to_row_stream(
                columns=struct.get_columns(),
            )
        else:
            row_stream = self.to_stream(
                stream_type=StreamType.RowStream,
                columns=struct.get_columns(),
            )
        return row_stream.structure(
            struct=struct,
            skip_bad_rows=skip_bad_rows,
            skip_bad_values=skip_bad_values,
            verbose=verbose,
        )

    def get_source_struct(self, default=None) -> Struct:
        source = self.get_source()
        if hasattr(source, 'get_struct'):
            return source.get_struct()
        else:
            return default

    def get_detected_struct(
            self,
            count: int = DEFAULT_DETECT_COUNT,
            set_types: Optional[dict] = None,
            default: Optional[StructInterface] = None,
    ) -> Struct:
        if hasattr(self, 'get_detected_columns'):
            columns = self.get_detected_columns(count)
        else:
            columns = self.get_columns()
        struct = fc.FlatStruct.get_struct_detected_by_title_row(columns)
        if struct:
            if set_types:
                struct.set_types(set_types)
            return struct
        else:
            return default

    def get_dataframe(self, columns: Optional[Iterable] = None) -> DataFrame:
        if pd and get_use_objects_for_output():
            if columns:
                dataframe = DataFrame(self.get_items(), columns=columns)
                columns = arg.get_names(columns)
                dataframe = dataframe[columns]
            else:
                dataframe = DataFrame(self.get_items())
            return dataframe

    def _get_field_getter(self, field: UniKey, item_type: Union[ItemType, Auto] = AUTO, default=None):
        if isinstance(self, RegularStreamInterface) or hasattr(self, 'get_item_type'):
            item_type = arg.delayed_acquire(item_type, self.get_item_type)
        return lambda i: fs.it.get_field_value_from_item(
            field=field, item=i, item_type=item_type,
            default=default, logger=self.get_selection_logger(),
        )

    def get_dict(self, key: UniKey, value: UniKey) -> dict:
        key_getter = self._get_field_getter(key)
        value_getter = self._get_field_getter(value)
        return {key_getter(i): value_getter(i) for i in self.get_items()}

    def get_str_description(self) -> str:
        return '{} rows, {} columns: {}'.format(
            self.get_str_count(),
            self.get_column_count(),
            ', '.join(self.get_columns()),
        )

    def get_str_headers(self) -> Iterable:
        yield "{}('{}') {}".format(self.__class__.__name__, self.get_name(), self.get_str_description())

    def get_one_item(self) -> Optional[Item]:
        one_item_stream = self.take(1)
        assert isinstance(one_item_stream, RegularStreamInterface)
        list_one_item = list(one_item_stream.get_items())
        if list_one_item:
            return list_one_item[0]
        else:
            return None

    def example(
            self, *filters, count: int = DEFAULT_SHOW_COUNT,
            allow_tee_iterator: bool = True,
            allow_spend_iterator: bool = True,
            **filter_kwargs
    ) -> Native:
        self.actualize()
        use_tee = allow_tee_iterator and hasattr(self, 'tee_stream')
        if self.is_in_memory() or (allow_spend_iterator and not use_tee):
            example = self.filter(*filters, **filter_kwargs).take(count)
        elif use_tee and hasattr(self, 'tee_stream'):
            assert hasattr(self, 'tee_stream')
            example = self.copy().take(count)
        else:  # keep safe items in iterator
            example = self.take(1)
        return self._assume_native(example)

    def get_demo_example(
            self, count: int = DEFAULT_SHOW_COUNT,
            as_dataframe: AutoBool = AUTO,
            filters: Optional[Array] = None, columns: Optional[Array] = None,
    ) -> Union[DataFrame, Iterable]:
        as_dataframe = arg.acquire(as_dataframe, get_use_objects_for_output())
        sm_sample = self.filter(*filters or []) if filters else self
        sm_sample = sm_sample.take(count)
        if hasattr(sm_sample, 'get_dataframe') and as_dataframe:
            return sm_sample.get_dataframe(columns)
        elif hasattr(sm_sample, 'select') and columns:
            return sm_sample.select(*columns).get_items()
        elif hasattr(sm_sample, 'get_items'):
            return sm_sample.get_items()

    def show(
            self,
            count: int = DEFAULT_SHOW_COUNT,
            filters: Columns = None,
            columns: Columns = None,
            as_dataframe: AutoBool = AUTO,
    ):
        self.log(self.get_str_description(), level=LOGGING_LEVEL_INFO, truncate=False, force=True)
        return self.get_demo_example(count=count, filters=filters, columns=columns, as_dataframe=as_dataframe)

    def describe(
            self, *filters,
            take_struct_from_source: bool = False,
            count: Count = DEFAULT_SHOW_COUNT,
            columns: Columns = None,
            show_header: bool = True,
            struct_as_dataframe: bool = False,
            separate_by_tabs: bool = False,
            allow_collect: bool = True,
            **filter_kwargs
    ):
        if show_header:
            for line in self.get_str_headers():
                self.log(line)
        example = self.example(*filters, **filter_kwargs, count=count)
        if hasattr(self, 'get_struct'):
            expected_struct = self.get_struct()
            source_str = 'native'
        elif take_struct_from_source:
            expected_struct = self.get_source_struct()
            source_str = 'from source {}'.format(self.get_source().__repr__())
        else:
            expected_struct = self.get_detected_struct()
            source_str = 'detected from example items'
        expected_struct = fc.FlatStruct.convert_to_native(expected_struct)
        detected_struct = example.get_detected_struct(count)
        detected_struct.validate_about(expected_struct)
        message = '{} {}'.format(source_str, expected_struct.get_validation_message())
        struct_as_dataframe = struct_as_dataframe and get_use_objects_for_output()
        struct_dataframe = expected_struct.describe(
            as_dataframe=struct_as_dataframe, show_header=False, logger=self.get_logger(),
            separate_by_tabs=separate_by_tabs, example=example.get_one_item(), comment=message,
        )
        if struct_as_dataframe:
            return struct_dataframe
        else:
            return example.get_demo_example(as_dataframe=get_use_objects_for_output())
