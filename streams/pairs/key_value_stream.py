try:  # Assume we're a sub-module in a package.
    from streams import stream_classes as sm
    from utils import arguments as arg
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from .. import stream_classes as sm
    from ...utils import arguments as arg


def is_pair(row):
    if isinstance(row, (list, tuple)):
        return len(row) == 2


def check_pairs(pairs, skip_errors=False):
    for i in pairs:
        if is_pair(i):
            pass
        elif skip_errors:
            continue
        else:
            raise TypeError('check_pairs(): this item is not pair: {}'.format(i))
        yield i


def get_key(pair):
    return pair[0]


class KeyValueStream(sm.RowStream):
    def __init__(
            self,
            data,
            count=None,
            less_than=None,
            check=True,
            secondary=None,
            source=None,
            context=None,
            max_items_in_memory=sm.MAX_ITEMS_IN_MEMORY,
            tmp_files_template=sm.TMP_FILES_TEMPLATE,
            tmp_files_encoding=sm.TMP_FILES_ENCODING,
    ):
        super().__init__(
            check_pairs(data) if check else data,
            count=count,
            less_than=less_than,
            check=check,
            source=source,
            context=context,
            max_items_in_memory=max_items_in_memory,
            tmp_files_template=tmp_files_template,
            tmp_files_encoding=tmp_files_encoding,
        )
        if secondary is None:
            self.secondary = sm.StreamType.AnyStream
        else:
            assert secondary in sm.StreamType
            self.secondary = secondary or sm.StreamType.AnyStream

    def is_valid_item(self, item):
        return is_pair(
            item,
        )

    def valid_items(self, items, skip_errors=False):
        return check_pairs(
            items,
            skip_errors,
        )

    def secondary_type(self):
        return self.secondary

    def secondary_stream(self):
        def get_values():
            for i in self.data:
                yield i[1]
        return sm.get_class(self.secondary)(
            list(get_values()) if self.is_in_memory() else get_values(),
            count=self.count,
        )

    def memory_sort_by_key(self, reverse=False):
        return self.memory_sort(
            key=get_key,
            reverse=reverse
        )

    def disk_sort_by_key(self, reverse=False, step=arg.DEFAULT):
        step = arg.undefault(step, self.max_items_in_memory)
        return self.disk_sort(
            key=get_key,
            reverse=reverse,
            step=step,
        )

    def sorted_group_by_key(self):
        def get_groups():
            accumulated = list()
            prev_k = None
            for k, v in self.data:
                if (k != prev_k) and accumulated:
                    yield prev_k, accumulated
                    accumulated = list()
                prev_k = k
                accumulated.append(v)
            yield prev_k, accumulated
        fx_groups = sm.KeyValueStream(
            get_groups(),
        )
        if self.is_in_memory():
            fx_groups = fx_groups.to_memory()
        return fx_groups

    def values(self):
        return self.secondary_stream()

    def keys(self):
        my_keys = list()
        for i in self.get_items():
            key = get_key(i)
            if key in my_keys:
                pass
            else:
                my_keys.append(key)
        return my_keys

    def extract_keys_in_memory(self):
        stream_for_keys, stream_for_items = self.tee(2)
        return (
            stream_for_keys.keys(),
            stream_for_items,
        )

    def extract_keys(self):
        if self.is_in_memory():
            return self.extract_keys_in_memory()
        else:
            return self.extract_keys_on_disk()

    def get_dict(self, of_lists=False):
        result = dict()
        if of_lists:
            for k, v in self.get_items():
                distinct = result.get(k, [])
                if v not in distinct:
                    result[k] = distinct + [v]
        else:
            for k, v in self.get_items():
                result[k] = v
        return result

    def to_records(self, key='key', value='value', **kwargs):
        function = kwargs.get('function') or (lambda i: {key: i[0], value: i[1]})
        return self.map_to_records(
            function,
        )
