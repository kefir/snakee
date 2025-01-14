from enum import Enum
from typing import Optional, Callable, Iterable, Iterator, Generator, Sequence, Union

try:  # Assume we're a submodule in a package.
    from interfaces import (
        LeafConnectorInterface, StructInterface, Stream, RegularStream,
        ConnType, LoggingLevel, ItemType, StreamType, JoinType,
        Context, Item, Name, FieldName, FieldNo, Links, Columns, OptionalFields, Array, ARRAY_TYPES,
    )
    from base.functions.arguments import (
        get_names, get_name, get_generated_name,
        get_str_from_args_kwargs, get_cropped_text,
    )
    from base.functions.errors import get_type_err_msg
    from base.constants.chars import EMPTY, ALL, CROP_SUFFIX, ITEMS_DELIMITER, SQL_INDENT
    from utils.decorators import deprecated
    from functions.primary.text import remove_extra_spaces
    from content.fields.any_field import AnyField
    from content.selection.abstract_expression import (
        AbstractDescription,
        SQL_FUNC_NAMES_DICT, SQL_TYPE_NAMES_DICT, CODE_HTML_STYLE,
    )
    from content.selection.concrete_expression import AliasDescription
    from content.struct.flat_struct import FlatStruct
    from content.documents.document_item import Paragraph, Sheet, Chapter
    from streams.interfaces.abstract_stream_interface import StreamInterface, DEFAULT_EXAMPLE_COUNT
    from streams.abstract.wrapper_stream import WrapperStream
    from streams.stream_builder import StreamBuilder
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...interfaces import (
        LeafConnectorInterface, StructInterface, Stream, RegularStream,
        ConnType, LoggingLevel, ItemType, StreamType, JoinType,
        Context, Item, Name, FieldName, FieldNo, Links, Columns, OptionalFields, Array, ARRAY_TYPES,
    )
    from ...base.functions.arguments import (
        get_names, get_name, get_generated_name,
        get_str_from_args_kwargs, get_cropped_text,
    )
    from ...base.functions.errors import get_type_err_msg
    from ...base.constants.chars import EMPTY, ALL, CROP_SUFFIX, ITEMS_DELIMITER, SQL_INDENT
    from ...utils.decorators import deprecated
    from ...functions.primary.text import remove_extra_spaces
    from ...content.fields.any_field import AnyField
    from ...content.selection.abstract_expression import (
        AbstractDescription,
        SQL_FUNC_NAMES_DICT, SQL_TYPE_NAMES_DICT, CODE_HTML_STYLE,
    )
    from ...content.selection.concrete_expression import AliasDescription
    from ...content.struct.flat_struct import FlatStruct
    from ...content.documents.document_item import Paragraph, Sheet, Chapter
    from ..interfaces.abstract_stream_interface import StreamInterface, DEFAULT_EXAMPLE_COUNT
    from ..abstract.wrapper_stream import WrapperStream
    from ..stream_builder import StreamBuilder

Native = WrapperStream
TableOrQuery = Union[LeafConnectorInterface, StreamInterface, None]

LINE_NO_LEN = 3
QUERY_LINE_LEN = 120
QUERY_SHEET_COLUMNS = ('no', LINE_NO_LEN), ('query', QUERY_LINE_LEN)
IS_DEFINED = '{field} <> 0 and {field} NOT NULL'
MSG_NOT_IMPL = '{method}() operation is not defined for SqlStream, try to use .to_record_stream().{method}() instead'
MONOSPACE_HTML_STYLE = 'font-family: monospace'

OUTPUT_STRUCT_COMPARISON_TAGS = dict(
    this_only='OUTPUT_ONLY', other_only='SOURCE_ONLY',
    this_duplicated='DUPLICATED_IN_OUTPUT', other_duplicated='DUPLICATED_IN_SOURCE',
    both_duplicated='DUPLICATED',
)


class SqlSection(Enum):
    Select = 'SELECT'
    From = 'FROM'
    Join = 'JOIN'
    Where = 'WHERE'
    GroupBy = 'GROUP BY'
    OrderBy = 'ORDER BY'
    Limit = 'LIMIT'


SECTIONS_ORDER = (
    SqlSection.Select, SqlSection.From, SqlSection.Join,
    SqlSection.Where, SqlSection.GroupBy, SqlSection.OrderBy, SqlSection.Limit,
)


class SqlStream(WrapperStream):
    def __init__(
            self,
            data: Links = None,
            name: Optional[Name] = None,
            caption: str = EMPTY,
            source: TableOrQuery = None,
            context: Context = None,
    ):
        if data is None:
            data = dict()
        if name is None:
            name = self._get_generated_name()
        self._count = None
        super().__init__(
            data=data, check=False,
            name=name, caption=caption,
            source=source, context=context,
        )

    @staticmethod
    def get_item_type() -> ItemType:
        return ItemType.Row

    def get_source_table(self) -> LeafConnectorInterface:
        source = self.get_source()
        if isinstance(source, LeafConnectorInterface):  # source.get_type() == ConnType.Table
            return source
        elif isinstance(source, SqlStream) or hasattr(source, 'get_source_table'):
            return source.get_source_table()
        else:
            arg = 'self.get_source()'
            expected = 'Table', SqlStream
            msg = get_type_err_msg(expected=expected, got=source, arg=arg, caller=self.get_source_table)
            raise TypeError(msg)

    def get_database(self):
        table = self.get_source_table()
        if hasattr(table, 'get_database'):
            return table.get_database()
        else:
            arg = 'self.get_source()'
            expected = 'Table', SqlStream
            msg = get_type_err_msg(expected=expected, got=table, arg=arg, caller=self.get_source_table)
            raise TypeError(msg)

    def close(self) -> int:
        return self.get_database().close()

    def execute_query(self, verbose: Optional[bool] = None) -> Iterable:
        db = self.get_database()
        return db.execute(self.get_query(), get_data=True, verbose=verbose)

    def get_expressions_for(self, section: SqlSection) -> list:
        if section == SqlSection.From:
            return [self.get_source()]
        children = self.get_data()
        if not children.get(section):
            children[section] = list()
        return children[section]

    def add_expression_for(
            self,
            section: SqlSection,
            expression: Union[FieldName, FieldNo, Array, LeafConnectorInterface, Native],
            inplace: bool = True,
    ) -> Native:
        if inplace:
            stream = self
        else:
            stream = self.copy()
        if section == SqlSection.From:
            expected = LeafConnectorInterface, SqlStream
            if isinstance(stream, expected):
                stream.set_source(expression, inplace=True)
            else:
                msg = get_type_err_msg(expected=expected, got=stream, arg='self', caller=self.add_expression_for)
                raise TypeError(msg)
        stream.get_expressions_for(section).append(expression)
        return stream

    def get_select_lines(self) -> Iterator[str]:
        descriptions = self.get_expressions_for(SqlSection.Select)
        if not descriptions:
            yield ALL
        for desc in descriptions:
            if isinstance(desc, FieldName):
                yield desc
            elif isinstance(desc, (AnyField, AbstractDescription)) or hasattr(desc, 'get_sql_expression'):
                yield desc.get_sql_expression()
            elif isinstance(desc, Sequence):
                target_field = desc[0]
                expression = desc[1:]
                if len(expression) == 1:
                    source_field = expression[0]
                    yield f'{source_field} AS {target_field}'
                elif len(expression) == 2:
                    if isinstance(expression[0], Callable):
                        function, source_field = expression
                    elif isinstance(expression[-1], Callable):
                        source_field, function = expression
                    else:
                        expected = 'tuple (function, *fields) or (*fields, function)'
                        msg = get_type_err_msg(expression, expected=expected, arg='expr', caller=self.get_select_lines)
                        raise TypeError(msg)
                    if hasattr(function, 'get_sql_expr'):
                        sql_function_expr = function.get_sql_expr(source_field)
                    else:
                        function_name = function.__name__
                        sql_type_name = SQL_TYPE_NAMES_DICT.get(function_name)
                        if sql_type_name:
                            sql_function_expr = f'{source_field}::{sql_type_name}'
                        else:
                            sql_function_name = SQL_FUNC_NAMES_DICT.get(function_name)
                            if not sql_function_name:
                                self.get_logger().warning(f'Unsupported function call: {function_name}')
                                sql_function_name = function_name
                            sql_function_expr = f'{sql_function_name}({source_field})'
                    yield f'{sql_function_expr} AS {target_field}'
                else:
                    if isinstance(expression[0], Callable):
                        function, *fields = expression
                    elif isinstance(expression[-1], Callable):
                        *fields, function = expression
                    else:
                        expected = 'tuple (function, *fields) or (*fields, function)'
                        msg = get_type_err_msg(expression, expected=expected, arg='expr', caller=self.get_select_lines)
                        raise TypeError(msg)
                    if hasattr(function, 'get_sql_expr'):
                        sql_function_expr = function.get_sql_expr(*fields)
                    else:
                        raise ValueError(f'Expected @sql_compatible function, got {function}')
                    yield f'{sql_function_expr} AS {target_field}'
            else:
                raise ValueError(f'expected field name or tuple, got {desc}')

    def get_where_lines(self) -> Iterator[str]:
        for description in self.get_expressions_for(SqlSection.Where):
            if isinstance(description, FieldName):
                yield IS_DEFINED.format(field=description)
            elif isinstance(description, (AnyField, AbstractDescription)) or hasattr(description, 'get_sql_expression'):
                yield description.get_sql_expression()
            elif isinstance(description, Sequence):
                target_field = description[0]
                expression = description[1:]
                if len(expression) == 1:
                    value = expression[0]
                    if isinstance(value, FieldName):
                        yield "{} = '{}'".format(target_field, value)
                    elif isinstance(value, Callable):
                        func = value
                        if hasattr(func, 'get_sql_expr'):
                            yield func.get_sql_expr(target_field)
                        else:
                            func_name = func.__name__
                            sql_func_name = SQL_FUNC_NAMES_DICT.get(func_name)
                            if not sql_func_name:
                                self.get_logger().warning('Unsupported function call: {}'.format(func_name))
                                sql_func_name = func_name
                            yield '{}({})'.format(sql_func_name, target_field)
                    else:
                        yield '{} = {}'.format(target_field, value)
                if len(expression) == 2:
                    raise NotImplemented(f'got {description}')
            else:
                raise ValueError(f'expected field name or tuple, got {description}')

    def get_from_lines(self, subquery_name: Optional[Name] = None) -> Iterator[str]:
        from_section = list(self.get_expressions_for(SqlSection.From))
        if len(from_section) == 1:
            from_obj = from_section[0]
            if subquery_name is None:
                if isinstance(from_obj, SqlStream) or hasattr(from_obj, 'get_query_name'):
                    subquery_name = from_obj.get_query_name()
            if not subquery_name:
                subquery_name = self._get_generated_name()
            if isinstance(from_obj, FieldName):
                yield from_obj
            elif hasattr(from_obj, 'get_path'):  # isinstance(from_obj, Table):
                yield from_obj.get_path()
            elif hasattr(from_obj, 'get_query_lines'):  # isinstance(from_obj, SqlTransform)
                yield '('
                yield from from_obj.get_query_lines(finish=False)
                yield f') AS {subquery_name}'
            else:
                raise ValueError(f'from-section data must be Table or Name(str), got {from_obj}')
        else:
            yield from from_section

    def get_join_lines(
            self,
            left_subquery_name: Optional[Name] = None,
            right_subquery_name: Optional[Name] = None,
    ) -> Iterator[str]:
        join_section = list(self.get_expressions_for(SqlSection.Join))
        if join_section:
            assert len(join_section) == 1
            indent = SQL_INDENT
            table_or_query, key, how = join_section[0]
            field_name = get_name(key)
            subquery_name = self._get_generated_name()
            if left_subquery_name is None:
                left_subquery_name = self.get_source().get_query_name()
            if right_subquery_name is None:
                if isinstance(table_or_query, SqlStream) or hasattr(table_or_query, 'get_query_name'):
                    right_subquery_name = table_or_query.get_query_name()
            if right_subquery_name is None:
                right_subquery_name = f'{subquery_name}_right'
            join_type_name = get_name(how).upper()
            section_title = f'{join_type_name} JOIN'
            if isinstance(table_or_query, FieldName):
                yield section_title
                yield indent + table_or_query
            elif hasattr(table_or_query, 'get_path'):  # isinstance(from_obj, Table):
                yield section_title
                yield indent + table_or_query.get_path()
            elif hasattr(table_or_query, 'get_query_lines'):  # isinstance(from_obj, SqlTransform)
                yield f'{section_title} ('
                yield from map(lambda s: f'{indent}{s}', table_or_query.get_query_lines(finish=False))
                yield f') AS {right_subquery_name}'
            else:
                raise ValueError('join-section data must be Table or Subquery, got {}'.format(table_or_query))
            yield f'ON {left_subquery_name}.{field_name} = {right_subquery_name}.{field_name}'

    def get_groupby_lines(self) -> Iterator[str]:
        for f in self.get_expressions_for(SqlSection.GroupBy):
            if isinstance(f, (AnyField, AbstractDescription)) or hasattr(f, 'get_sql_expression'):
                yield f.get_sql_expression()
            else:
                yield get_name(f)

    def get_orderby_lines(self) -> Iterator[str]:
        for f in self.get_expressions_for(SqlSection.OrderBy):
            if isinstance(f, (AnyField, AbstractDescription)) or hasattr(f, 'get_sql_expression'):
                yield f.get_sql_expression()
            else:
                yield get_name(f)

    def get_limit_lines(self) -> Iterator[str]:
        yield from self.get_expressions_for(SqlSection.Limit)

    def get_section_lines(self, section: SqlSection) -> Iterable:
        method_name = 'get_{}_lines'.format(get_name(section).lower())
        method = self.__getattribute__(method_name)
        yield from method()

    def get_one_line_query(self, finish: bool = True) -> str:
        query = self.get_query(finish=finish)
        return remove_extra_spaces(query)

    def get_query(self, finish: bool = True) -> str:
        return '\n'.join(list(self.get_query_lines(finish=finish)))

    def get_query_lines(self, finish: bool = True) -> list[str]:
        query_lines = list()
        for section in SECTIONS_ORDER:
            lines = self.get_section_lines(section)
            query_lines = list(self._format_section_lines(section, lines))
        if finish:
            query_lines += ';'
        return query_lines

    def get_query_records(self) -> Iterator[dict]:
        for n, e in enumerate(self.get_query_lines()):
            yield dict(no=n + 1, query=e)

    def get_query_name(self) -> str:
        return self.get_name().split('.')[-1].split(':')[-1]

    @staticmethod
    def _get_generated_name() -> str:
        return get_generated_name('subquery', include_random=True, include_datetime=False)

    @staticmethod
    def _format_section_lines(section: SqlSection, lines: Iterable) -> Iterator[str]:
        lines = list(lines)
        if lines:
            section_name = section.value
            if section == SqlSection.Join:
                indent = EMPTY
            else:
                indent = SQL_INDENT
                yield section_name
            if section == SqlSection.Where:
                delimiter = f'\n{indent}AND '
            elif section in (SqlSection.From, SqlSection.Join):
                delimiter = EMPTY
            else:
                delimiter = ITEMS_DELIMITER
            for n, line in enumerate(lines):
                is_last = n == len(lines) - 1
                yield f'{indent}{line}' if is_last else f'{indent}{line}{delimiter}'

    def has_any_section(self) -> bool:
        for section in SECTIONS_ORDER:
            if section != SqlSection.From:
                if self.get_expressions_for(section):
                    return True
        return False

    def new(self, **kwargs):
        if 'source' not in kwargs:
            kwargs['source'] = self
        return self.__class__(**kwargs)

    def copy(self) -> Native:
        data = self._data.copy()
        stream = self.make_new(data)
        return self._assume_native(stream)

    def select(self, *fields, **expressions) -> Native:
        select_section = self.get_expressions_for(SqlSection.Select)
        if select_section:
            return self.new().select(*fields, **expressions)
        else:
            stream = self.copy()
            assert isinstance(stream, SqlStream) or hasattr(stream, 'add_expression_for'), f'got {stream}'
            list_expressions = list(fields)
            for target, source in expressions.items():
                if isinstance(source, ARRAY_TYPES):
                    list_expressions.append((target, *source))
                else:
                    list_expressions.append((target, source))
            for expression in list_expressions:
                stream.add_expression_for(SqlSection.Select, expression)
            return stream

    def filter(self, *fields, **expressions) -> Native:
        if self.has_any_section():
            return self.new().filter(*fields, **expressions)
        else:
            stream = self.copy()
            assert isinstance(stream, SqlStream) or hasattr(stream, 'add_expression_for'), f'got {stream}'
            list_expressions = list(fields) + [(field, value) for field, value in expressions.items()]
            for expressions in list_expressions:
                stream.add_expression_for(SqlSection.Where, expressions)
            return stream

    def group_by(self, *fields, values: Optional[list] = None) -> Native:
        if values:
            columns = self.get_input_columns()
            assert min([c in columns for c in get_names(values)])
        select_section = self.get_expressions_for(SqlSection.Select)
        groupby_section = self.get_expressions_for(SqlSection.GroupBy)
        if select_section or groupby_section:
            stream = self.new().group_by(*fields)
        else:
            stream = self.copy()
            assert isinstance(stream, SqlStream) or hasattr(stream, 'add_expression_for'), f'got {stream}'
            for f in fields:
                stream.add_expression_for(SqlSection.GroupBy, f)
        if values:
            assert isinstance(stream, SqlStream) or hasattr(stream, 'select'), f'got {stream}'
            stream = stream.select(*fields, *values)
        return stream

    def sort(self, *fields) -> Native:
        stream = self.copy()
        assert isinstance(stream, SqlStream) or hasattr(stream, 'add_expression_for'), f'got {stream}'
        for f in fields:
            stream.add_expression_for(SqlSection.OrderBy, f)
        return stream

    def join(self, table_or_stream: TableOrQuery, key: AnyField, how: JoinType = JoinType.Left) -> Native:
        assert isinstance(key, (AnyField, str)), f'got {key}'
        if self.has_any_section():
            return self.new().join(table_or_stream, key=key, how=how)
        else:
            stream = self.copy()
            join_tuple = (table_or_stream, key, how)
            stream.add_expression_for(SqlSection.Join, join_tuple)
        return stream

    def take(self, count: int) -> Native:
        return self.add_expression_for(SqlSection.Limit, count, inplace=False)

    def get_count(self, recalc: bool = False) -> Optional[int]:
        if self._count:
            return self._count
        elif recalc:
            transform = self.select(cnt=(len, ALL))
            assert isinstance(transform, SqlStream)
            data = transform.execute_query()
            count = list(data)[0]
            self._count = count
            return count

    def get_items(self) -> Iterable:
        return self.execute_query()

    def map(self, function: Callable) -> Native:
        raise NotImplementedError(MSG_NOT_IMPL.format(method='map'))

    def skip(self, count: int) -> Native:
        raise NotImplementedError(MSG_NOT_IMPL.format(method='map'))

    def get_source_table_struct(self) -> StructInterface:
        source = self.get_source_table().get_struct()
        return source

    def get_input_struct(self, skip_missing: bool = False) -> Optional[StructInterface]:
        source = self.get_source()
        if isinstance(source, SqlStream) or hasattr(source, 'get_output_struct'):
            return source.get_output_struct(skip_missing=skip_missing)
        elif isinstance(source, LeafConnectorInterface) or hasattr(source, 'get_struct'):
            return source.get_struct()
        elif not skip_missing:
            expected = SqlSection, LeafConnectorInterface
            msg = get_type_err_msg(expected=expected, got=source, arg='source', caller=self.get_input_struct)
            raise TypeError(msg)

    def get_output_struct(self, skip_missing: bool = False) -> StructInterface:
        output_columns = self.get_output_columns(skip_missing=skip_missing)
        if output_columns is not None:
            input_struct = self.get_input_struct(skip_missing=skip_missing)
            output_struct = FlatStruct(output_columns)
            if input_struct:
                types = {f: t for f, t in input_struct.get_types_dict().items() if f in output_columns}
                output_struct = output_struct.set_types(types)
                assert isinstance(output_struct, FlatStruct), get_type_err_msg(output_struct, FlatStruct, 'output')
                output_struct.compare_with(input_struct, tags=OUTPUT_STRUCT_COMPARISON_TAGS, set_valid=True)
            return output_struct

    def get_input_columns(self, skip_missing: bool = False) -> Columns:
        source = self.get_source()
        expected = SqlStream, LeafConnectorInterface
        if isinstance(source, expected) or hasattr(source, 'get_columns'):
            return source.get_columns(skip_missing=skip_missing)
        else:
            arg = 'self.get_source()'
            msg = get_type_err_msg(expected=expected, got=source, arg=arg, caller=self.get_input_columns)
            raise TypeError(msg)

    def get_output_columns(self, skip_missing: bool = False) -> Columns:
        columns = self.get_selected_columns()
        if columns is None:
            columns = self.get_input_columns(skip_missing=skip_missing)
        if columns is not None:
            join_expressions = self.get_expressions_for(SqlSection.Join)
            if join_expressions:
                join_tuple = join_expressions[0]
                join_columns = join_tuple[0].get_columns(skip_missing=skip_missing)
                if join_columns:
                    for c in join_columns:
                        if c not in columns:
                            columns.append(c)
        return columns

    def get_selected_columns(self) -> Columns:
        select_expressions = self.get_expressions_for(SqlSection.Select)
        if select_expressions:
            columns = list()
            for i in select_expressions:
                if isinstance(i, AbstractDescription):
                    columns.append(i.get_target_field_name())
                elif isinstance(i, AnyField):
                    columns.append(i.get_name())
                elif len(i) == 1 or isinstance(i, FieldName):
                    if i == ALL or i[0] == ALL:
                        for source_column in self.get_input_columns():
                            columns.append(source_column)
                    else:
                        columns.append(i)
                elif len(i) > 1:
                    columns.append(i[0])
                else:
                    raise ValueError(i)
            return columns

    def get_columns(self, skip_missing: bool = False) -> Columns:
        return self.get_output_columns(skip_missing=skip_missing)

    def get_struct(self) -> StructInterface:
        return self.get_output_struct()

    def get_rows(self, verbose: bool = True) -> Iterable:
        return self.execute_query(verbose=verbose)

    def get_records(self) -> Iterable:
        columns = self.get_output_columns()
        return map(lambda r: dict(zip(columns, r)), self.get_rows())

    def to_row_stream(self) -> Stream:
        return self.to_stream(self.get_rows(), item_type=ItemType.Row)

    def to_record_stream(self) -> Stream:
        return self.to_stream(self.get_records(), item_type=ItemType.Record)

    def to_stream(
            self,
            data: Optional[Iterable] = None,
            item_type: ItemType = ItemType.Auto,
            ex: OptionalFields = None,
            **kwargs
    ) -> Union[RegularStream, Native]:
        if item_type in (ItemType.Auto, None):
            item_type = self.get_stream_type()
        if data:
            stream_class = StreamBuilder.get_default_stream_class()
            meta = self.get_compatible_meta(stream_class, ex=ex)
            meta.update(kwargs)
            if 'count' not in meta:
                meta['count'] = self.get_count()
            if 'source' not in meta:
                meta['source'] = self.get_source()
            return stream_class(data, **meta)
        elif item_type == StreamType.SqlStream:
            return self
        else:
            method_suffix = StreamType.of(item_type).get_method_suffix()
            method_name = f'to_{method_suffix}'
            stream_method = self.__getattribute__(method_name)
            return stream_method()

    def collect(self, item_type: ItemType = ItemType.Record) -> Stream:
        stream = self.to_stream(item_type=item_type).collect()
        return self._assume_native(stream)

    def one(self) -> Stream:
        stream = self.copy().take(1)
        if isinstance(stream, SqlStream) or hasattr(stream, 'collect'):
            return stream.collect()
        else:
            msg = get_type_err_msg(expected=SqlStream, got=stream, arg='self.copy().take(1)', caller=self.one)
            raise TypeError(msg)

    def get_one_item(self) -> Item:
        items = self.one().get_items()
        return list(items)[0]

    def get_stream_representation(self) -> str:
        source = self.get_source()
        if isinstance(source, SqlStream) or hasattr(source, 'get_stream_representation'):
            sm_repr = source.get_stream_representation()
        else:
            sm_repr = repr(source)
        filter_expressions = self.get_expressions_for(SqlSection.Where)
        if filter_expressions:
            str_filter_expressions = list()
            for i in filter_expressions:
                if isinstance(i, (AbstractDescription, AnyField)) or hasattr(i, 'get_brief_repr'):
                    str_filter_expressions.append(i.get_brief_repr())
                elif isinstance(i, ARRAY_TYPES):
                    str_filter_expressions.append('{}={}'.format(get_name(i[0]), repr(i[1]) if len(i) == 2 else i[1:]))
            sm_repr += '.filter({})'.format(ITEMS_DELIMITER.join(str_filter_expressions))
        groupby_expressions = self.get_expressions_for(SqlSection.GroupBy)
        if groupby_expressions:
            sm_repr += '.group_by({})'.format(ITEMS_DELIMITER.join(get_names(groupby_expressions)))
        sort_expressions = self.get_expressions_for(SqlSection.OrderBy)
        if sort_expressions:
            sm_repr += '.sort({})'.format(ITEMS_DELIMITER.join(get_names(sort_expressions)))
        select_expressions = self.get_expressions_for(SqlSection.Select)
        if select_expressions:
            str_select_expressions = list()
            for i in select_expressions:
                if isinstance(i, (AbstractDescription, AnyField)) or hasattr(i, 'get_brief_repr'):
                    str_select_expressions.append(i.get_brief_repr())
                elif isinstance(i, ARRAY_TYPES):
                    name = get_name(i[0])
                    value = repr(i[1]) if len(i) == 2 else i[1:]
                    str_select_expressions.append(f'{name}={value}')
            str_select_line = ITEMS_DELIMITER.join(str_select_expressions)
            sm_repr += f'.select({str_select_line})'
        return sm_repr

    def get_struct_sheet(self, name: str = 'Columns sheet') -> Union[Sheet, Paragraph]:
        struct = self.get_output_struct(skip_missing=True)
        if isinstance(struct, StructInterface) or hasattr(struct, 'get_data_sheet'):
            return struct.get_data_sheet(name=name)
        else:
            return Paragraph([f'Undefined struct: {struct}'])

    def get_struct_chapter(self, name='Columns') -> Chapter:
        chapter = Chapter(name=name)
        title = Paragraph(['Columns'], level=3)
        chapter.append(title, inplace=True)
        output_columns = self.get_output_columns(skip_missing=True)
        input_struct = self.get_source_table().get_struct()
        caption = Paragraph([f'Expected output columns: {output_columns}', f'Expected input struct: {input_struct}'])
        chapter.append(caption, inplace=True)
        chapter.append(self.get_struct_sheet(name=f'{name} sheet'), inplace=True)
        return chapter

    def get_str_headers(self, comment: str = '') -> Iterator[str]:
        yield self.get_stream_representation()
        if comment:
            yield comment

    def get_description_lines(self) -> Iterator[str]:
        yield repr(self)
        yield self.get_stream_representation()
        yield '\nGenerated SQL query:\n'
        yield from self.get_query_lines()
        yield '\nExpected output columns: {}'.format(self.get_output_columns())
        yield 'Expected input struct: {}'.format(self.get_source_table().get_struct())
        struct = self.get_struct()
        if hasattr(struct, 'get_struct_repr_lines'):
            yield from struct.get_struct_repr_lines(select_fields=self.get_output_columns())

    def get_description_items(
            self,
            comment: Optional[str] = None,
            depth: int = 2,
            enumerated: bool = False,
            **kwargs
    ) -> Generator:
        assert not kwargs, f'{self.__class__.__name__}.get_description_items(): kwargs not supported'
        yield Paragraph([self.get_query_name()], level=1, name='Title')
        yield Paragraph(self.get_str_headers(comment=comment))
        yield Paragraph(['Generated SQL query'], level=3)
        if enumerated:
            query_records = self.get_query_records()
            yield Sheet.from_records(query_records, columns=QUERY_SHEET_COLUMNS, style=MONOSPACE_HTML_STYLE)
        else:
            query_lines = self.get_query_lines()
            yield Paragraph(query_lines, style=CODE_HTML_STYLE, name='SQL query lines')
        yield self.get_struct_chapter()

    @staticmethod
    def _assume_native(stream) -> Native:
        return stream
