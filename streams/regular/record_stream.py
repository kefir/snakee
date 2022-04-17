from typing import Optional, Iterable, Callable, Union

try:  # Assume we're a submodule in a package.
    from interfaces import (
        Stream, RegularStream, RowStream, KeyValueStream, StructStream, FieldInterface,
        ItemType, StreamType,
        Context, Connector, AutoConnector, LeafConnectorInterface, TmpFiles,
        Count, Name, Field, Columns, Array, ARRAY_TYPES,
        AUTO, Auto, AutoCount, AutoName, AutoBool,
    )
    from base.functions.arguments import get_name, get_names, update
    from utils.external import pd, DataFrame, get_use_objects_for_output
    from utils.decorators import deprecated_with_alternative
    from functions.secondary import all_secondary_functions as fs
    from content.selection import selection_classes as sn, selection_functions as sf
    from content.items.item_getters import value_from_record, tuple_from_record, filter_items
    from streams.mixin.convert_mixin import ConvertMixin
    from streams.mixin.columnar_mixin import ColumnarMixin
    from streams.regular.any_stream import AnyStream
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...interfaces import (
        Stream, RegularStream, RowStream, KeyValueStream, StructStream, FieldInterface,
        ItemType, StreamType,
        Context, Connector, AutoConnector, LeafConnectorInterface, TmpFiles,
        Count, Name, Field, Columns, Array, ARRAY_TYPES,
        AUTO, Auto, AutoCount, AutoName, AutoBool,
    )
    from ...base.functions.arguments import get_name, get_names, update
    from ...utils.external import pd, DataFrame, get_use_objects_for_output
    from ...utils.decorators import deprecated_with_alternative
    from ...functions.secondary import all_secondary_functions as fs
    from ...content.selection import selection_classes as sn, selection_functions as sf
    from ...content.items.item_getters import value_from_record, tuple_from_record, filter_items
    from ..mixin.convert_mixin import ConvertMixin
    from ..mixin.columnar_mixin import ColumnarMixin
    from .any_stream import AnyStream

Native = RegularStream

DEFAULT_EXAMPLE_COUNT = 10
DEFAULT_ANALYZE_COUNT = 100


class RecordStream(AnyStream, ColumnarMixin, ConvertMixin):
    def __init__(
            self,
            data: Iterable,
            name: AutoName = AUTO,
            caption: str = '',
            count: Count = None,
            less_than: Count = None,
            source: Connector = None,
            context: Context = None,
            max_items_in_memory: AutoCount = AUTO,
            tmp_files: TmpFiles = AUTO,
            check: bool = True,
    ):
        super().__init__(
            data=data, check=check,
            name=name, caption=caption,
            count=count, less_than=less_than,
            source=source, context=context,
            max_items_in_memory=max_items_in_memory,
            tmp_files=tmp_files,
        )

    @staticmethod
    def get_item_type() -> ItemType:
        return ItemType.Record

    def _get_key_function(self, descriptions: Array, take_hash: bool = False) -> Callable:
        descriptions = get_names(descriptions)
        if len(descriptions) == 0:
            raise ValueError('key must be defined')
        elif len(descriptions) == 1:
            key_function = fs.partial(value_from_record, descriptions[0])
        else:
            key_function = fs.partial(tuple_from_record, descriptions)
        if take_hash:
            return lambda r: hash(key_function(r))
        else:
            return key_function

    def get_one_column_values(self, column: Field, as_list: bool = False) -> Iterable:
        column = get_name(column)
        if as_list:
            return list(self.get_one_column_values(column, as_list=False))
        else:
            for r in self.get_records():
                yield r.get(column)

    def get_detected_columns(self, by_items_count: int = DEFAULT_ANALYZE_COUNT, sort: bool = True) -> Iterable:
        example = self.example(count=by_items_count)
        columns = set()
        for r in example.get_items():
            columns.update(r.keys())
        if sort:
            columns = sorted(columns)
        return columns

    def get_columns(self, by_items_count: int = DEFAULT_ANALYZE_COUNT) -> Iterable:
        return self.get_detected_columns(by_items_count=by_items_count)

    def get_records(self, columns: Union[Iterable, Auto] = AUTO) -> Iterable:
        if columns == AUTO:
            return self.get_items()
        else:
            columns = get_names(columns)
            return self.select(*columns).get_items()

    def get_enumerated_records(self, field: str = '#', first: int = 1) -> Iterable:
        for n, r in enumerate(self.get_data()):
            r[field] = n + first
            yield r

    def enumerate(self, native: bool = False) -> Stream:
        if native:
            return self.stream(
                self.get_enumerated_records(),
            )
        else:
            return self.stream(
                self._get_enumerated_items(),
                stream_type=StreamType.KeyValueStream,
                secondary=self.get_stream_type(),
            )

    def select(self, *fields, use_extended_method: bool = False, **expressions) -> Native:
        selection_mapper = sn.get_selection_function(
            *fields, **expressions,
            target_item_type=ItemType.Record, input_item_type=ItemType.Record,
            logger=self.get_logger(), selection_logger=self.get_selection_logger(),
            use_extended_method=use_extended_method,
        )
        stream = self.map(selection_mapper)
        return self._assume_native(stream)

    def filter(self, *fields, **expressions) -> Native:
        filter_function = filter_items(*fields, **expressions, item_type=ItemType.Record, skip_errors=True)
        filtered_items = self._get_filtered_items(filter_function)
        if self.is_in_memory():
            filtered_items = list(filtered_items)
            count = len(filtered_items)
            less_than = count
        else:
            count = None
            less_than = self.get_estimated_count()
        stream = self.stream(filtered_items, count=count, less_than=less_than)
        return stream

    def add_column(self, name: Field, values: Iterable, ignore_errors: bool = False) -> Native:
        name = get_name(name)
        items = map(lambda i, v: fs.merge_two_items()(i, {name: v}), self.get_items(), values)
        stream = self.stream(items)
        if self.is_in_memory():
            if not ignore_errors:
                if not isinstance(values, ARRAY_TYPES):
                    values = list(values)
                msg = 'for add_column() stream and values must have same items count, got {} != {}'
                assert self.get_count() == len(values), msg.format(self.get_count(), len(values))
            stream = stream.to_memory()
        return stream

    def sort(self, *keys, reverse: bool = False, step: AutoCount = AUTO, verbose: bool = True) -> Native:
        key_function = self._get_key_function(keys)
        step = Auto.delayed_acquire(step, self.get_limit_items_in_memory)
        if self.can_be_in_memory(step=step):
            stream = self.memory_sort(key_function, reverse, verbose=verbose)
        else:
            stream = self.disk_sort(key_function, reverse, step=step, verbose=verbose)
        return self._assume_native(stream)

    def sorted_group_by(
            self,
            *keys,
            values: Columns = None,
            as_pairs: bool = False,
            skip_missing: bool = False,
    ) -> Stream:
        keys = update(keys)
        keys = get_names(keys, or_callable=True)
        values = get_names(values)
        key_function = self._get_key_function(keys)
        iter_groups = self._get_groups(key_function, as_pairs=as_pairs)
        if as_pairs:
            stream_class = StreamType.KeyValueStream.get_class()
            stream_groups = stream_class(iter_groups, value_stream_type=StreamType.RowStream)
        else:
            stream_class = StreamType.RowStream.get_class()
            stream_groups = stream_class(iter_groups, check=False)
        if values:
            item_type = self.get_item_type()  # ItemType.Record
            fold_mapper = fs.fold_lists(keys=keys, values=values, skip_missing=skip_missing, item_type=item_type)
            stream_groups = stream_groups.map_to_type(fold_mapper, stream_type=StreamType.RecordStream)
        if self.is_in_memory():
            return stream_groups.to_memory()
        else:
            stream_groups.set_estimated_count(self.get_count() or self.get_estimated_count())
            return stream_groups

    def group_by(
            self,
            *keys,
            values: Columns = None,
            as_pairs: bool = False,
            take_hash: bool = True,
            step: AutoCount = AUTO,
            verbose: bool = True,
    ) -> Stream:
        keys = update(keys)
        keys = get_names(keys)
        values = get_names(values)
        if hasattr(keys[0], 'get_field_names'):  # if isinstance(keys[0], FieldGroup)
            keys = keys[0].get_field_names()
        step = Auto.delayed_acquire(step, self.get_limit_items_in_memory)
        if as_pairs:
            key_for_sort = keys
        else:
            key_for_sort = self._get_key_function(keys, take_hash=take_hash)
        sorted_stream = self.sort(
            key_for_sort,
            step=step,
            verbose=verbose,
        )
        grouped_stream = sorted_stream.sorted_group_by(
            keys,
            values=values,
            as_pairs=as_pairs,
        )
        return grouped_stream

    def group_to_pairs(
            self, *keys, values: Columns = None,
            step: AutoCount = AUTO, verbose: bool = True,
    ) -> KeyValueStream:
        grouped_stream = self.group_by(*keys, values=values, step=step, as_pairs=True, take_hash=False, verbose=verbose)
        return self._assume_pairs(grouped_stream)

    def _get_uniq_records(self, *keys) -> Iterable:
        keys = update(keys)
        key_fields = get_names(keys)
        key_function = self._get_key_function(key_fields)
        prev_value = AUTO
        for r in self.get_records():
            value = key_function(r)
            if value != prev_value:
                yield r
            prev_value = value

    def uniq(self, *keys, sort: bool = False) -> Native:
        if sort:
            stream = self.sort(*keys)
        else:
            stream = self
        result = self.stream(stream._get_uniq_records(*keys), count=None)
        return self._assume_native(result)

    def get_dataframe(self, columns: Columns = None) -> DataFrame:
        if pd and get_use_objects_for_output():
            dataframe = DataFrame(self.get_items())
            if Auto.is_defined(columns):
                columns = get_names(columns)
                dataframe = dataframe[columns]
            return dataframe

    def get_demo_example(
            self, count: Count = DEFAULT_EXAMPLE_COUNT,
            filters: Columns = None, columns: Columns = None,
            as_dataframe: AutoBool = AUTO,
    ) -> Union[DataFrame, list, None]:
        as_dataframe = Auto.acquire(as_dataframe, get_use_objects_for_output())
        sm_sample = self.filter(*filters) if filters else self
        sm_sample = sm_sample.take(count)
        if as_dataframe:
            return sm_sample.get_dataframe(columns)
        elif hasattr(sm_sample, 'get_list'):
            return sm_sample.get_list()

    def get_rows(self, columns: Union[Columns, Auto] = AUTO, add_title_row=False) -> Iterable:
        columns = Auto.delayed_acquire(columns, self.get_columns)
        columns = get_names(columns)
        if add_title_row:
            yield columns
        for r in self.get_items():
            yield [r.get(c) for c in columns]

    def to_row_stream(self, *columns, **kwargs) -> RowStream:
        add_title_row = kwargs.pop('add_title_row', None)
        kwarg_columns = kwargs.pop('columns', None)
        if kwarg_columns:
            msg = 'columns can be provided by args or kwargs, not both (got args={}, kwargs.columns={})'
            assert not columns, msg.format(columns, kwarg_columns)
            columns = kwarg_columns
        if columns == [AUTO]:
            columns = AUTO
        assert columns, 'columns for convert RecordStream to RowStream must be defined'
        if kwargs:
            raise ValueError('to_row_stream(): {} arguments are not supported'.format(kwargs.keys()))
        count = self.get_count()
        less_than = self.get_estimated_count()
        if add_title_row:
            if count:
                count += 1
            if less_than:
                less_than += 1
        rows = self.get_rows(columns=columns, add_title_row=add_title_row)  # tmp for debug
        stream = self.stream(
            rows,
            stream_type=StreamType.RowStream,
            count=count,
            less_than=less_than,
        )
        return self._assume_native(stream)

    def get_key_value_pairs(self, key: Field, value: Field, **kwargs) -> Iterable:
        for i in self.get_records():
            k = value_from_record(i, key, **kwargs)
            v = i if value is None else value_from_record(i, value, **kwargs)
            yield k, v

    def to_key_value_stream(self, key: Field = 'key', value: Field = None, skip_errors: bool = False) -> KeyValueStream:
        kwargs = dict(logger=self.get_logger(), skip_errors=skip_errors)
        pairs = self.get_key_value_pairs(key, value, **kwargs)
        stream = self.stream(
            list(pairs) if self.is_in_memory() else pairs,
            stream_type=StreamType.KeyValueStream,
            value_stream_type=StreamType.RecordStream if value is None else StreamType.AnyStream,
            check=False,
        )
        return self._assume_pairs(stream)

    def to_file(self, file: Connector, verbose: bool = True, return_stream: bool = True) -> Native:
        if not (isinstance(file, LeafConnectorInterface) or hasattr(file, 'write_stream')):
            raise TypeError('Expected TsvFile, got {} as {}'.format(file, type(file)))
        meta = self.get_meta()
        file.write_stream(self, verbose=verbose)
        if return_stream:
            return file.to_record_stream(verbose=verbose).update_meta(**meta)

    @deprecated_with_alternative('RecordStream.to_file()')
    def to_tsv_file(self, *args, **kwargs) -> Stream:
        return self.to_file(*args, **kwargs)

    def to_column_file(
            self, filename: str, columns: Union[Iterable, Auto] = AUTO,
            add_title_row=True, delimiter='\t',
            check=True, verbose=True, return_stream=True,
    ) -> Optional[Native]:
        meta = self.get_meta()
        sm_csv_file = self.to_row_stream(
            columns=columns,
            add_title_row=add_title_row,
        ).to_line_stream(
            delimiter=delimiter,
        ).to_text_file(
            filename,
            check=check,
            verbose=verbose,
            return_stream=return_stream,
        )
        if return_stream:
            return sm_csv_file.skip(
                1 if add_title_row else 0,
            ).to_row_stream(
                delimiter=delimiter,
            ).to_record_stream(
                columns=columns,
            ).update_meta(
                **meta
            )

    @classmethod
    def from_column_file(
            cls,
            filename, columns, delimiter='\t',
            skip_first_line=True, check=AUTO,
            expected_count=AUTO, verbose=True,
    ) -> Native:
        stream_class = StreamType.LineStream.get_class()
        return stream_class.from_text_file(
            filename, skip_first_line=skip_first_line,
            check=check, expected_count=expected_count, verbose=verbose,
        ).to_row_stream(
            delimiter=delimiter,
        ).to_record_stream(
            columns=columns,
        )

    @classmethod
    def from_json_file(
            cls, filename,
            default_value=None, max_count=None,
            check=True, verbose=False,
    ) -> Native:
        stream_class = StreamType.LineStream.get_class()
        parsed_stream = stream_class.from_text_file(
            filename,
            max_count=max_count, check=check, verbose=verbose,
        ).parse_json(
            default_value=default_value,
            to=StreamType.RecordStream,
        )
        return parsed_stream

    @staticmethod
    def _assume_native(stream) -> Native:
        return stream

    @staticmethod
    def _assume_pairs(stream) -> KeyValueStream:
        return stream

    def get_dict(
            self,
            key: Union[Field, Columns],
            value: Union[Field, Columns, None] = None,
            of_lists: bool = False,
            skip_errors: bool = False,
    ) -> dict:
        key = get_names(key)
        key_value_stream = self.to_key_value_stream(key, value, skip_errors=skip_errors)
        return key_value_stream.get_dict(of_lists=of_lists)

    def get_str_description(self) -> str:
        return '{} rows, {} columns: {}'.format(
            self.get_str_count(),
            self.get_column_count(),
            ', '.join([str(c) for c in self.get_columns()]),
        )

    def __str__(self):
        title = self.__repr__()
        description = self.get_description()
        if description:
            return '<{title} {desc}>'.format(title=title, desc=description)
        else:
            return '<{}>'.format(title)
