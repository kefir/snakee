from abc import ABC
from typing import Union, Iterable, Generator, Callable, Optional

try:  # Assume we're a submodule in a package.
    from interfaces import (
        Context, LoggerInterface, SelectionLogger, ExtLogger, LoggingLevel,
        Stream, RegularStream, RegularStreamInterface, StructStream, StructInterface, ColumnarInterface,
        StreamType, ItemType, JoinType, How,
        Count, UniKey, Item, Array, Columns, OptionalFields,
    )
    from base.functions.arguments import get_name, get_names, update
    from base.mixin.iter_data_mixin import IterDataMixin
    from functions.secondary.item_functions import composite_key, merge_two_items, items_to_dict
    from content.fields import field_classes as fc
    from content.items.item_getters import get_filter_function
    from content.documents.document_item import Paragraph, Chapter
    from utils import algo
    from utils.decorators import deprecated, deprecated_with_alternative
    from utils.external import pd, DataFrame, get_use_objects_for_output
    from streams.interfaces.abstract_stream_interface import DEFAULT_EXAMPLE_COUNT
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...interfaces import (
        Context, LoggerInterface, SelectionLogger, ExtLogger, LoggingLevel,
        Stream, RegularStream, RegularStreamInterface, StructStream, StructInterface, ColumnarInterface,
        StreamType, ItemType, JoinType, How,
        Count, UniKey, Item, Array, Columns, OptionalFields,
    )
    from ...base.functions.arguments import get_name, get_names, update
    from ...base.mixin.iter_data_mixin import IterDataMixin
    from ...functions.secondary.item_functions import composite_key, merge_two_items, items_to_dict
    from ...content.fields import field_classes as fc
    from ...content.items.item_getters import get_filter_function
    from ...content.documents.document_item import Paragraph, Chapter
    from ...utils import algo
    from ...utils.decorators import deprecated, deprecated_with_alternative
    from ...utils.external import pd, DataFrame, get_use_objects_for_output
    from ..interfaces.abstract_stream_interface import DEFAULT_EXAMPLE_COUNT

Native = Union[RegularStreamInterface, ColumnarInterface]
Struct = Optional[StructInterface]

SAFE_COUNT_ITEMS_IN_MEMORY = 10000
DEFAULT_DETECT_COUNT = 100
SKIP_COLUMNS = '*', '-', ''


class ColumnarMixin(IterDataMixin, ABC):
    @classmethod
    def is_valid_item(cls, item: Item) -> bool:
        return cls.get_item_type().isinstance(item)

    @classmethod
    def get_validated(cls, items: Iterable, skip_errors: bool = False, context: Context = None) -> Generator:
        for i in items:
            if cls.is_valid_item(i):
                yield i
            else:
                item_type = cls.get_item_type()
                message = f'get_validated(): item {i} is not a {item_type}'
                if skip_errors:
                    if context:
                        context.get_logger().log(message, level=LoggingLevel.Info)
                else:
                    raise TypeError(message)

    def validated(self, skip_errors: bool = False) -> Native:
        stream = self.stream(
            self.get_validated(self.get_items(), skip_errors=skip_errors),
        )
        return self._assume_native(stream)

    # @deprecated_with_alternative('having_columns()')
    def assert_has_columns(self, *columns, skip_columns=SKIP_COLUMNS, skip_missing: bool = False, **kwargs) -> Native:
        return self.having_columns(*columns, skip_columns=skip_columns, skip_missing=skip_missing, **kwargs)

    def having_columns(self, *columns, skip_columns=SKIP_COLUMNS, skip_missing: bool = False, **kwargs) -> Native:
        skip_columns_names = get_names(skip_columns, or_callable=False)
        existing_column_names = get_names(self.get_columns(**kwargs), or_callable=False)
        missing_columns = list()
        for c in columns:
            c_name = get_name(c)
            if c_name not in skip_columns_names:
                if c_name not in existing_column_names:
                    missing_columns.append(c)
        if missing_columns:
            missing_column_names = get_names(missing_columns, or_callable=False)
            missing_str = ', '.join(missing_column_names)
            existing_str = ', '.join(existing_column_names)
            dataset = repr(self)
            msg = f'{dataset} has no declared columns: [{missing_str}]; existing columns are [{existing_str}]'
            if skip_missing:
                self.log(msg, level=LoggingLevel.Warning)
            else:
                raise AssertionError(msg)
        return self

    def get_shape(self) -> tuple:
        return self.get_count(), self.get_column_count()

    @deprecated
    def get_description(self) -> str:
        rows = self.get_str_count()
        cols = self.get_column_count()
        column_names = ', '.join(self.get_columns())
        return f'{rows} rows, {cols} columns: {column_names}'

    def get_column_count(self) -> int:
        return len(list(self.get_columns()))

    def _get_items_of_type(self, item_type: ItemType) -> Iterable:
        if item_type in (ItemType.Auto, None):
            is_native_type = True
        elif hasattr(self, 'get_item_type'):
            is_native_type = item_type == self.get_item_type()
        else:
            is_native_type = False
        if is_native_type:
            return self.get_items()
        elif hasattr(self, 'get_items_of_type'):
            return self.get_items_of_type(item_type)
        else:
            formatter = '{obj} is not supporting items converting from {src} to {dst}'
            if hasattr(self, 'get_item_type'):
                src = self.get_item_type()
            else:
                src = repr(self)
            msg = formatter.format(obj=self, src=src, dst=item_type)
            raise AttributeError(msg)

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
            logger: Optional[LoggerInterface] = None,
            **kwargs
    ) -> Iterable:
        if logger is None:
            logger = self.get_logger()
        if item_type in (ItemType.Auto, None):
            item_type = self.get_item_type()
        filter_function = get_filter_function(
            *args, **kwargs, item_type=item_type,
            skip_errors=skip_errors, logger=logger,
        )
        return filter(filter_function, self._get_items_of_type(item_type))

    def filter(self, *args, item_type: ItemType = ItemType.Auto, skip_errors: bool = False, **kwargs) -> Native:
        if item_type in (ItemType.Auto, None):
            item_type = self.get_item_type()
        filtered_items = self._get_filtered_items(*args, item_type=item_type, skip_errors=skip_errors, **kwargs)
        stream = self.to_stream(data=filtered_items, item_type=item_type)
        return self._assume_native(stream)

    def _get_flat_mapped_items(self, function: Callable) -> Generator:
        for i in self.get_items():
            yield from function(i)

    def flat_map(self, function: Callable, inplace: bool = False) -> Optional[Native]:
        items = self._get_flat_mapped_items(function=function)
        return self.set_items(items, inplace=inplace)

    @deprecated_with_alternative('map_to_type()')
    def map_to(self, function: Callable, item_type: ItemType) -> Stream:
        items = map(function, self.get_items())
        stream = self.stream(items, item_type=item_type)
        return self._assume_native(stream)

    def map_side_join(
            self,
            right: Native,
            key: UniKey,
            how: How = JoinType.Left,
            right_is_uniq: bool = True,
            merge_function: Optional[Callable] = None,
            inplace: bool = False,
    ) -> Optional[Native]:
        keys = update([key])
        keys = get_names(keys, or_callable=True)
        item_type = self.get_item_type()
        key_function = composite_key(*keys, item_type=item_type)
        if merge_function is None:
            merge_function = merge_two_items(item_type=item_type)
        if not isinstance(how, JoinType):
            how = JoinType(how)
        right_items = list(right.get_items())
        if right_items:
            joined_items = algo.map_side_join(
                iter_left=self.get_items(),
                iter_right=right_items,
                key_function=key_function,
                merge_function=merge_function,
                dict_function=items_to_dict(),
                how=how,
                uniq_right=right_is_uniq,
            )
        else:  # right is empty
            if how in (JoinType.Left, JoinType.Outer, JoinType.Full):
                joined_items = self.get_items()
            else:  # JoinType.Right, JoinType.Inner
                joined_items = list()
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
        keys = get_names(keys, or_callable=True)
        keys = update(keys)
        values = get_names(values, or_callable=True)
        return self.sort(*keys).sorted_group_by(*keys, values=values, as_pairs=as_pairs)

    def apply_to_stream(self, function: Callable, *args, **kwargs) -> Stream:
        return function(self, *args, **kwargs)

    def get_selection_logger(self) -> SelectionLogger:
        if hasattr(self, 'get_context'):
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
            row_stream = self.to_row_stream(columns=struct.get_columns())
        else:
            row_stream = self.to_stream(item_type=ItemType.Row, columns=struct.get_columns())
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
                columns = get_names(columns, or_callable=False)
                dataframe = dataframe[columns]
            else:
                dataframe = DataFrame(self.get_items())
            return dataframe

    def _get_field_getter(self, field: UniKey, item_type: ItemType = ItemType.Auto, default=None):
        if isinstance(self, RegularStreamInterface) or hasattr(self, 'get_item_type') and hasattr(self, 'get_struct'):
            if item_type in (ItemType.Auto, None):
                item_type = self.get_item_type()
            struct = self.get_struct()
        else:
            struct = None
        return item_type.get_field_getter(field=field, struct=struct, default=default)

    def get_dict(self, key: UniKey, value: UniKey) -> dict:
        key_getter = self._get_field_getter(key)
        value_getter = self._get_field_getter(value)
        return {key_getter(i): value_getter(i) for i in self.get_items()}

    def get_str_description(self) -> str:
        rows = self.get_str_count()
        cols = self.get_column_count()
        column_names = ', '.join(self.get_columns())
        return f'{rows} rows, {cols} columns: {column_names}'

    def get_str_headers(self) -> Iterable[str]:
        cls_name = self.__class__.__name__
        obj_name = self.get_name()
        state = self.get_str_description()
        yield f'{cls_name}({repr(obj_name)}) {state}'

    def get_one_item(self) -> Optional[Item]:
        one_item_stream = self.take(1)
        assert isinstance(one_item_stream, RegularStreamInterface)
        list_one_item = list(one_item_stream.get_items())
        if list_one_item:
            return list_one_item[0]
        else:
            return None

    def example(
            self,
            *filters,
            count: int = DEFAULT_EXAMPLE_COUNT,
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
            self,
            count: int = DEFAULT_EXAMPLE_COUNT,
            filters: Optional[Array] = None,
            columns: Optional[Array] = None,
            verbose: Optional[bool] = None,
    ) -> Union[DataFrame, Iterable]:
        sm_sample = self.filter(*filters or []) if filters else self
        sm_sample = sm_sample.take(count)
        sm_sample = sm_sample.to_record_stream(verbose=verbose)
        if hasattr(sm_sample, 'select') and columns:
            return sm_sample.select(*columns).get_items()
        elif hasattr(sm_sample, 'get_items'):
            return sm_sample.get_items()

    def show(
            self,
            count: int = DEFAULT_EXAMPLE_COUNT,
            filters: Columns = None,
            columns: Columns = None,
    ):
        display = self.get_display()
        display.append(self.get_str_description())
        demo_example = self.get_demo_example(count=count, filters=filters, columns=columns)
        demo_example = list(demo_example)
        if demo_example:
            if columns is None:
                if isinstance(demo_example[0], dict):
                    columns = demo_example[0].keys()
                else:
                    return display.display_paragraph(demo_example)
            return display.display_sheet(demo_example, columns=columns)
        else:
            return display.display_paragraph('[EMPTY] Demo example is empty.')

    def get_data_chapter(self, example, name: str = 'Rows sample') -> Chapter:
        chapter = Chapter()
        title = Paragraph(name, level=3, name=f'{name} title')
        chapter.append(title, inplace=True)
        if hasattr(example, 'get_data_sheet'):
            data_sheet = example.get_data_sheet()
        elif hasattr(self, 'get_data_sheet'):
            data_sheet = self.get_data_sheet()
        else:
            msg = f'Expected obj or example having .get_data_sheet()-method, got example={example}, obj={self}'
            raise TypeError(msg)
        chapter.append(data_sheet, inplace=True)
        return chapter

    def get_struct_chapter(self, example, take_struct_from_source: bool = False, name: str = 'Columns') -> Chapter:
        chapter = Chapter()
        title = Paragraph(name, level=3, name=f'{name} title')
        chapter.append(title, inplace=True)
        if hasattr(self, 'get_struct'):
            expected_st = self.get_struct()
            source_str = 'native'
        elif take_struct_from_source:
            expected_st = self.get_source_struct()
            source_str = f'from source {repr(self.get_source())}'
        else:
            expected_st = self.get_detected_struct()
            source_str = 'detected from example items'
        detected_st = example.get_detected_struct()  # count = ALL
        if expected_st:
            expected_st = fc.FlatStruct.convert_to_native(expected_st)
            assert isinstance(expected_st, fc.FlatStruct) or hasattr(expected_st, 'display_data_sheet'), expected_st
            assert isinstance(detected_st, fc.FlatStruct) or hasattr(expected_st, 'validate_about'), detected_st
            detected_st.validate_about(expected_st)
            validation_message = f'{source_str} {expected_st.get_validation_message()}'
            struct_sheet = expected_st.get_data_sheet(example=example.get_one_item(), name=f'{name} sheet')
        elif detected_st:
            validation_message = 'Expected struct not defined, displaying detected struct:'
            assert isinstance(detected_st, fc.FlatStruct) or hasattr(detected_st, 'display_data_sheet'), detected_st
            struct_sheet = expected_st.get_data_sheet(example=example.get_one_item(), name=f'{name} sheet')
        else:
            validation_message = '[EMPTY] Struct is not detected.'
            struct_sheet = None
        if validation_message:
            validation_paragraph = Paragraph(validation_message, name=f'{name} validation message')
            chapter.append(validation_paragraph, inplace=True)
        if struct_sheet:
            chapter.append(struct_sheet, inplace=True)
        return chapter

    def get_description_items(
            self,
            count: Count = DEFAULT_EXAMPLE_COUNT,
            comment: Optional[str] = None,
            depth: int = 1,
            take_struct_from_source: bool = False,
            filters: Optional[Iterable] = None,
            named_filters: Optional[dict] = None,
    ) -> Generator:
        display = self.get_display()
        yield display.build_paragraph(self.get_name(), level=1)
        headers = list(self.get_str_headers())
        if comment:
            headers.append(comment)
        yield display.build_paragraph(headers)
        example = self.example(*filters, **named_filters, count=count)
        yield self.get_struct_chapter(example=example, take_struct_from_source=take_struct_from_source)
        yield self.get_data_chapter(example=example)

    def describe(
            self,
            *filters,
            take_struct_from_source: bool = False,
            count: Count = DEFAULT_EXAMPLE_COUNT,
            columns: Columns = None,
            comment: Optional[str] = None,
            allow_collect: bool = True,
            depth: int = 1,
            display=None,
            **filter_kwargs
    ) -> Native:
        display = self.get_display(display)
        for i in self.get_description_items(
            comment=comment, depth=depth,
            take_struct_from_source=take_struct_from_source,
            filters=filters, named_filters=filter_kwargs,
        ):
            display.display_item(i)
        return self
