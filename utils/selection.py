from typing import Callable, Union, Any

try:  # Assume we're a sub-module in a package.
    from utils import (
        algo,
        arguments as arg,
        items as it,
    )
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from . import (
        algo,
        arguments as arg,
        items as it,
    )

Description = Union[Callable, list, tuple]

IGNORE_CYCLIC_DEPENDENCIES = False
PRIMITIVE_TYPES = str, int, float, bool


def process_description(d) -> tuple:
    if isinstance(d, Callable):
        function, inputs = d, list()
    elif isinstance(d, (list, tuple)):
        if callable(d[0]):
            function, inputs = d[0], d[1:]
        elif callable(d[-1]):
            inputs, function = d[:-1], d[-1]
        else:
            inputs, function = d, lambda *a: tuple(a)
    else:
        inputs, function = [d], lambda v: v
    return function, inputs


def topologically_sorted(expressions: dict, ignore_cycles: bool = IGNORE_CYCLIC_DEPENDENCIES, logger=None) -> list:
    unordered_fields = list()
    unresolved_dependencies = dict()
    for field, description in expressions.items():
        unordered_fields.append(field)
        _, dependencies = process_description(description)
        unresolved_dependencies[field] = [
            d for d in dependencies
            if d in expressions.keys() and d != field
        ]
    ordered_fields = algo.topologically_sorted(
        nodes=unordered_fields,
        edges=unresolved_dependencies,
        ignore_cycles=ignore_cycles,
        logger=logger,
    )
    return [(f, expressions[f]) for f in ordered_fields]


def flatten_descriptions(*fields, **expressions) -> list:
    descriptions = list(fields)
    logger = expressions.pop('logger', None)
    ignore_cycles = logger is not None
    for k, v in topologically_sorted(expressions, ignore_cycles=ignore_cycles, logger=logger):
        if isinstance(v, list):
            descriptions.append([k] + v)
        elif isinstance(v, tuple):
            descriptions.append([k] + list(v))
        else:
            descriptions.append([k] + [v])
    return descriptions


def safe_apply_function(function: Callable, fields, values, item=None, logger=None, skip_errors=True) -> Any:
    item = item or dict()
    try:
        return function(*values)
    except TypeError or ValueError as e:
        if logger:
            if hasattr(logger, 'log_selection_error'):
                logger.log_selection_error(function, fields, values, item, e)
            else:
                level = 30 if skip_errors else 40
                message = 'Error while processing function {} over fields {} with values {}.'
                logger.log(msg=message.format(function.__name__, fields, values), level=level)
        if not skip_errors:
            raise e


def value_from_row(row: Union[list, tuple], description: Description, logger=None, skip_errors=True) -> Any:
    if isinstance(description, Callable):
        return description(row)
    elif isinstance(description, (list, tuple)):
        function, columns = process_description(description)
        values = [row[f] for f in columns]
        return safe_apply_function(function, columns, values, item=row, logger=logger, skip_errors=skip_errors)
    elif isinstance(description, int):
        return row[description]
    else:
        message = 'field description must be int, callable or tuple ({} as {} given)'
        raise TypeError(message.format(description, type(description)))


def value_from_struct_row(row, description: Description, logger=None, skip_errors=True) -> Any:
    if callable(description):
        return description(row)
    elif isinstance(description, (int, str)):
        return row.get_value(description)
    elif isinstance(description, (list, tuple)):
        function, fields = process_description(description)
        values = [row.get_value(c) for c in fields]
        return safe_apply_function(function, fields, values, item=row, logger=logger, skip_errors=skip_errors)


def value_from_record(record: dict, description: Description, logger=None, skip_errors=True) -> Any:
    if callable(description):
        return description(record)
    elif isinstance(description, (list, tuple)):
        function, fields = process_description(description)
        values = [record.get(f) for f in fields]
        return safe_apply_function(function, fields, values, item=record, logger=logger, skip_errors=skip_errors)
    elif hasattr(description, 'get_names'):
        return [record.get(n) for n in description.get_names()]
    elif hasattr(description, 'get_name'):
        return record.get(description.get_name())
    else:
        return record.get(description)


def value_from_any(item, description: Description, logger=None, skip_errors=True) -> Any:
    if callable(description):
        return description(item)
    elif isinstance(description, (list, tuple)):
        function, fields = process_description(description)
        values = it.get_fields_values_from_item(fields, item)
        return safe_apply_function(function, fields, values, item=item, logger=logger, skip_errors=skip_errors)
    else:
        return it.get_field_value_from_item(description, item)


def value_from_item(item, description: Description, item_type=arg.AUTO, logger=None, skip_errors=True, default=None):
    if hasattr(description, 'get_name'):
        description = description.get_name()
    if callable(description):
        return description(item)
    elif isinstance(description, (int, str)):
        return it.get_field_value_from_item(
            field=description, item=item, item_type=item_type,
            skip_errors=skip_errors, logger=logger, default=default,
        )
    elif isinstance(description, (list, tuple)):
        function, fields = process_description(description)
        values = it.get_fields_values_from_item(
            fields, item, item_type=item_type,
            skip_errors=skip_errors, logger=logger, default=default,
        )
        return safe_apply_function(function, fields, values, item=item, logger=logger, skip_errors=skip_errors)
    else:
        message = 'field description must be int, callable or tuple ({} as {} given)'
        raise TypeError(message.format(description, type(description)))


def get_composite_key(item, keys_descriptions: list, item_type=arg.AUTO, logger=None, skip_errors=True) -> tuple:
    keys_descriptions = arg.update(keys_descriptions)
    keys_descriptions = [d.get_field_names() if hasattr(d, 'get_field_names') else d for d in keys_descriptions]
    result = list()
    for d in keys_descriptions:
        if isinstance(d, Callable):
            value = d(item)
        else:
            value = value_from_item(item, d, item_type=item_type, logger=logger, skip_errors=skip_errors)
        result.append(value)
    return tuple(result)


def tuple_from_record(record: dict, descriptions: list, logger=None) -> tuple:
    return tuple([value_from_record(record, d, logger=logger) for d in descriptions])


def row_from_row(row_in: Union[list, tuple], *descriptions) -> tuple:
    row_out = [None] * len(descriptions)
    c = 0
    for d in descriptions:
        if d == it.STAR:
            row_out = row_out[:c] + list(row_in) + row_out[c + 1:]
            c += len(row_in)
        else:
            row_out[c] = value_from_row(row_in, d)
            c += 1
    return tuple(row_out)


def row_from_any(item_in, *descriptions) -> tuple:
    row_out = [None] * len(descriptions)
    c = 0
    for desc in descriptions:
        if desc == it.STAR:
            if it.ItemType.Row.isinstance(item_in):
                row_out = row_out[:c] + list(item_in) + row_out[c + 1:]
                c += len(item_in)
            else:
                row_out[c] = item_in
                c += 1
        else:
            row_out[c] = value_from_any(item_in, desc)
            c += 1
    return tuple(row_out)


def record_from_any(item_in, *descriptions, logger=None) -> dict:
    rec_out = dict()
    for desc in descriptions:
        assert isinstance(desc, (list, tuple)) and len(desc) > 1, 'for AnyStream items description {} is not applicable'
        f_out = desc[0]
        if len(desc) == 2:
            f_in = desc[1]
            if callable(f_in):
                rec_out[f_out] = f_in(item_in)
            else:
                rec_out[f_out] = rec_out.get(f_in)
        else:
            fs_in = desc[1:]
            rec_out[f_out] = value_from_record(rec_out, fs_in, logger=logger)
    return rec_out


def record_from_record(rec_in: dict, *descriptions, logger=None) -> dict:
    record = rec_in.copy()
    fields_out = list()
    for desc in descriptions:
        if desc == it.STAR:
            fields_out += list(rec_in.keys())
        elif isinstance(desc, (list, tuple)):
            if len(desc) > 1:
                f_out = desc[0]
                fs_in = desc[1] if len(desc) == 2 else desc[1:]
                record[f_out] = value_from_record(record, fs_in, logger=logger)
                fields_out.append(f_out)
            else:
                raise ValueError('incorrect field description: {}'.format(desc))
        else:  # desc is field name
            if hasattr(desc, 'get_name'):  # isinstance(desc, FieldInterface)
                desc = desc.get_name()
            if desc not in record:
                record[desc] = None
            fields_out.append(desc)
    return {f: record[f] for f in fields_out}


def auto_to_auto(item, *descriptions, logger=None) -> Any:
    item_type = it.ItemType.detect(item, default=it.ItemType.Any)
    if item_type == it.ItemType.Record:
        return record_from_record(item, *descriptions, logger=logger)
    elif item_type == it.ItemType.Row:
        return row_from_row(item, *descriptions)
    else:
        return get_composite_key(item, descriptions)


def select(
        *fields,
        target_item_type=arg.AUTO, input_item_type=arg.AUTO,
        logger=None, selection_logger=arg.AUTO,
        **expressions
):
    descriptions = flatten_descriptions(
        *fields,
        logger=logger,
        **expressions
    )
    if target_item_type == it.ItemType.Record and input_item_type == it.ItemType.Record:
        return lambda r: record_from_record(r, *descriptions, logger=selection_logger)
    elif target_item_type == it.ItemType.Row and input_item_type == it.ItemType.Row:
        return lambda r: row_from_row(r, *descriptions)
    elif target_item_type == it.ItemType.Row and input_item_type == it.ItemType.Any:
        return lambda i: row_from_any(i, *descriptions)
    elif target_item_type == it.ItemType.Record and input_item_type == it.ItemType.Any:
        return lambda i: record_from_any(i, *descriptions, logger=logger)
    else:
        return lambda i: auto_to_auto(i, *descriptions, logger=logger)


def filter_items(*fields, item_type=arg.AUTO, skip_errors=False, logger=None, **expressions) -> Callable:
    expressions_list = [
        (k, (lambda i, v=v: i == v) if isinstance(v, PRIMITIVE_TYPES) else v)
        for k, v in expressions.items()
    ]
    extended_filters_list = list(fields) + expressions_list
    return lambda i: apply_filter_list_to_item(
        item=i, filter_list=extended_filters_list,
        item_type=item_type, skip_errors=skip_errors, logger=logger,
    )


def apply_filter_list_to_item(
        item, filter_list, item_type=arg.AUTO,
        skip_errors=False, logger=None,
) -> bool:
    for filter_desc in filter_list:
        if not value_from_item(item, filter_desc, item_type=item_type, logger=logger, skip_errors=skip_errors):
            return False
    return True
