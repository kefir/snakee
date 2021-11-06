from typing import Optional, Iterable, Generator, Union, Any
import os
import gzip as gz

try:  # Assume we're a sub-module in a package.
    from utils import arguments as arg
    from interfaces import (
        Context, Connector, ConnectorInterface, StructInterface, IterableStreamInterface,
        ContentType, ItemType,
        AUTO, Auto, AutoCount, AutoBool,
    )
    from connectors.abstract.leaf_connector import LeafConnector
    from connectors.content_format.content_classes import (
        AbstractFormat, ParsedFormat, LeanFormat,
        TextFormat, ColumnarFormat, FlatStructFormat,
        ContentType,
    )
    from connectors.mixin.connector_format_mixin import ConnectorFormatMixin
    from connectors.mixin.actualize_mixin import ActualizeMixin
    from connectors.mixin.stream_file_mixin import StreamFileMixin
    from streams.mixin.iterable_mixin import IterableStreamMixin
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...utils import arguments as arg
    from ...interfaces import (
        Context, Connector, ConnectorInterface, StructInterface, IterableStreamInterface,
        ContentType, ItemType,
        AUTO, Auto, AutoCount, AutoBool,
    )
    from ..abstract.leaf_connector import LeafConnector
    from ..content_format.content_classes import (
        AbstractFormat, ParsedFormat, LeanFormat,
        TextFormat, ColumnarFormat, FlatStructFormat,
        ContentType,
    )
    from ..mixin.connector_format_mixin import ConnectorFormatMixin
    from ..mixin.actualize_mixin import ActualizeMixin
    from ..mixin.stream_file_mixin import StreamFileMixin
    from ...streams.mixin.iterable_mixin import IterableStreamMixin

Stream = IterableStreamInterface
Struct = Optional[StructInterface]
Native = Union[LeafConnector, Stream]

CHUNK_SIZE = 8192
LOGGING_LEVEL_INFO = 20
LOGGING_LEVEL_WARN = 30


class LocalFile(LeafConnector, ConnectorFormatMixin, StreamFileMixin, ActualizeMixin, IterableStreamMixin):
    def __init__(
            self,
            name: str,
            content_format: Union[AbstractFormat, Auto] = AUTO,
            struct: Union[Struct, Auto, None] = AUTO,
            folder: Connector = None,
            context: Context = AUTO,
            expected_count: AutoCount = AUTO,
            verbose: AutoBool = AUTO,
    ):
        if folder:
            message = 'only LocalFolder supported for *File instances (got {})'.format(type(folder))
            assert isinstance(folder, ConnectorInterface) or folder.is_folder(), message
        else:
            folder = context.get_job_folder()
        self._declared_format = None
        self._detected_format = None
        self._fileholder = None
        self._modification_ts = None
        self._count = expected_count
        super().__init__(name=name, parent=folder, verbose=verbose)
        content_format = arg.delayed_acquire(content_format, LeanFormat.detect_by_name, name)
        assert isinstance(content_format, AbstractFormat)
        self.set_content_format(content_format, inplace=True)
        if struct is not None:
            if struct == AUTO:
                if isinstance(content_format, ColumnarFormat) or hasattr(content_format, 'is_first_line_title'):
                    if content_format.is_first_line_title():
                        struct = self.get_detected_struct_by_title_row()
            if arg.is_defined(struct, check_name=False):
                self.set_struct(struct, inplace=True)

    def get_content_format(self) -> AbstractFormat:
        return self.get_detected_format()

    def set_content_format(self, content_format: AbstractFormat, inplace: bool) -> Optional[Native]:
        return self.set_detected_format(content_format=content_format, inplace=inplace)

    def get_detected_format(self) -> AbstractFormat:
        return self._detected_format

    def set_detected_format(self, content_format: AbstractFormat, inplace: bool) -> Optional[Native]:
        if inplace:
            self._detected_format = content_format
            if not self.get_declared_format():
                self.set_declared_format(content_format, inplace=True)
        else:
            return self.make_new(content_format=content_format)

    def get_declared_format(self) -> AbstractFormat:
        return self._declared_format

    def set_declared_format(self, initial_format: AbstractFormat, inplace: bool) -> Optional[Native]:
        if inplace:
            self._declared_format = initial_format.copy()
        else:
            new = self.copy()
            assert isinstance(new, LocalFile)
            new.set_declared_format(initial_format, inplace=True)
            return new

    def get_content_type(self) -> ContentType:
        # return self._content_type
        return self.get_content_format().get_content_type()

    def get_encoding(self) -> Optional[str]:
        content_format = self.get_content_format()
        if hasattr(content_format, 'get_encoding'):
            return content_format.get_encoding()

    def get_ending(self) -> str:
        content_format = self.get_content_format()
        if hasattr(content_format, 'get_ending'):
            return content_format.get_ending()
        else:
            return TextFormat().get_ending()

    def get_folder(self) -> Union[Connector, Any]:
        return self.get_parent()

    def get_children(self) -> dict:
        return self._data

    def get_links(self) -> dict:
        return self.get_children()

    def get_prev_modification_timestamp(self) -> Optional[float]:
        return self._modification_ts

    def set_prev_modification_timestamp(self, timestamp: float) -> Native:
        self._modification_ts = timestamp
        return self

    def get_expected_count(self) -> Union[int, arg.Auto, None]:
        return self._count

    def set_count(self, count: int) -> Native:
        self._count = count
        return self

    def get_fileholder(self):
        return self._fileholder

    def set_fileholder(self, fileholder, inplace: bool = False) -> Optional[Native]:
        self._fileholder = fileholder
        if not inplace:
            return self

    def add_to_folder(self, folder: Connector) -> Native:
        assert isinstance(folder, ConnectorInterface), 'folder must be a LocalFolder (got {})'.format(type(folder))
        assert folder.is_folder(), 'folder must be a LocalFolder (got {})'.format(type(folder))
        folder.add_child(self)
        return self

    def get_default_file_extension(self) -> str:
        return self.get_content_type().get_default_file_extension()

    def is_directly_in_parent_folder(self) -> bool:
        return self.get_path_delimiter() in self.get_name()

    def has_path_from_root(self) -> bool:
        name = self.get_name()
        if isinstance(name, str):
            return name.startswith(self.get_path_delimiter()) or ':' in name

    def get_path(self) -> str:
        if self.has_path_from_root() or not self.get_folder():
            return self.get_name()
        else:
            folder_path = self.get_folder().get_path()
            if '*' in folder_path:
                folder_path = folder_path.replace('*', '{}')
            if arg.is_formatter(folder_path):
                return folder_path.format(self.get_name())
            elif folder_path.endswith(self.get_path_delimiter()):
                return folder_path + self.get_name()
            elif folder_path:
                return '{}{}{}'.format(folder_path, self.get_path_delimiter(), self.get_name())
            else:
                return self.get_name()

    def get_list_path(self) -> Iterable:
        return self.get_path().split(self.get_path_delimiter())

    def get_folder_path(self) -> str:
        return self.get_path_delimiter().join(self.get_list_path()[:-1])

    def is_inside_folder(self, folder: Union[str, Connector, Auto] = AUTO) -> bool:
        folder_obj = arg.acquire(folder, self.get_folder())
        if isinstance(folder_obj, str):
            folder_path = folder_obj
        else:  # elif isinstance(folder_obj, LocalFolder)
            folder_path = folder_obj.get_path()
        return self.get_folder_path() in folder_path

    def is_opened(self) -> bool:
        if self.get_fileholder() is None:
            return False
        else:
            return not self.is_closed()

    def is_closed(self) -> bool:
        fileholder = self.get_fileholder()
        if hasattr(fileholder, 'closed'):
            return fileholder.closed

    def close(self) -> int:
        if self.is_opened():
            self.get_fileholder().close()
            closed_count = 1
        else:
            closed_count = 0
        return closed_count

    def open(self, mode: str = 'r', allow_reopen: bool = False) -> Native:
        is_opened = self.is_opened()
        if is_opened or is_opened is None:
            if allow_reopen:
                self.close()
            else:
                raise AttributeError('File {} is already opened'.format(self.get_name()))
        path = self.get_path()
        if self.is_gzip():
            fileholder = gz.open(path, mode)
        else:
            params = dict()
            encoding = self.get_encoding()
            if encoding:
                params['encoding'] = encoding
            fileholder = open(path, mode, **params) if encoding else open(path, 'r')
        self.set_fileholder(fileholder)
        return self

    def remove(self, log: bool = True, verbose: bool = True) -> int:
        file_path = self.get_path()
        level = LOGGING_LEVEL_WARN if verbose else LOGGING_LEVEL_INFO
        if log:
            self.get_logger().log('Trying remove {}...'.format(file_path), level=level)
        os.remove(file_path)
        if log or verbose:
            self.get_logger().log('Successfully removed {}.'.format(file_path), level=level)
        return 1

    def is_existing(self) -> bool:
        return os.path.exists(self.get_path())

    def is_empty(self) -> bool:
        count = self.get_count(allow_slow_gzip=False) or 0
        return count <= 0

    def has_data(self) -> bool:
        if self.is_existing():
            return not self.is_empty()
        return False

    def is_in_memory(self) -> bool:
        return False

    @staticmethod
    def is_file() -> bool:
        return True

    def is_text_file(self) -> bool:
        return self.get_content_format().is_text()

    def get_modification_timestamp(self, reset: bool = True) -> Optional[float]:
        if self.is_existing():
            timestamp = os.path.getmtime(self.get_path())
            if reset or not self.get_prev_modification_timestamp():
                self.set_prev_modification_timestamp(timestamp)
            return timestamp

    def get_first_line(self, close: bool = True) -> str:
        assert self.is_existing(), 'For receive first line file/object must be existing: {}'.format(self)
        content_format = self.get_content_format()
        assert isinstance(content_format, ParsedFormat), 'For get first line content must be parsed: {}'.format(self)
        assert content_format.get_defined().is_text(), 'For parse content format must be text: {}'.format(self)
        assert not self.is_empty(), 'For get line file/object must be non-empty: {}'.format(self)
        lines = self.get_lines(skip_first=False, check=False, verbose=False)
        try:
            first_line = next(lines)
        except StopIteration:
            raise ValueError('Received empty content: {}'.format(self))
        if close:
            self.close()
        return first_line

    def get_next_lines(self, count: Optional[int] = None, skip_first: bool = False, close: bool = False) -> Iterable:
        is_opened = self.is_opened()
        if is_opened is not None:
            assert is_opened, 'File must be opened for get_next_lines(), got is_opened={}'.format(is_opened)
        encoding = self.get_encoding()
        ending = self.get_ending()
        iter_lines = self.get_fileholder()
        for n, line in enumerate(iter_lines):
            if skip_first and n == 0:
                continue
            if isinstance(line, bytes):
                line = line.decode(encoding) if encoding else line.decode()
            if ending:
                line = line.rstrip(ending)
            yield line
            if arg.is_defined(count):
                if count > 0 and (n + 1 == count):
                    break
        if close:
            self.close()

    def get_lines(
            self,
            count: Optional[int] = None,
            skip_first: bool = False, allow_reopen: bool = True,
            check: bool = True, verbose: AutoBool = AUTO,
            message: Union[str, Auto] = AUTO, step: AutoCount = AUTO,
    ) -> Iterable:
        if check and not self.is_gzip():
            # assert self.get_count(allow_reopen=True) > 0
            assert not self.is_empty(), 'for get_lines() file must be non-empty: {}'.format(self)
        self.open(allow_reopen=allow_reopen)
        lines = self.get_next_lines(count=count, skip_first=skip_first, close=True)
        verbose = arg.acquire(verbose, self.is_verbose())
        if verbose or arg.is_defined(message):
            message = arg.acquire(message, 'Reading {}')
            if '{}' in message:
                message = message.format(self.get_name())
            logger = self.get_logger()
            assert hasattr(logger, 'progress'), '{} has no progress in {}'.format(self, logger)
            if not count:
                count = self.get_count(allow_slow_gzip=False)
            lines = self.get_logger().progress(lines, name=message, count=count, step=step)
        return lines

    def get_items(
            self,
            verbose: AutoBool = AUTO,
            step: AutoCount = AUTO,
    ) -> Iterable:
        return self.get_items_of_type(item_type=AUTO, verbose=verbose, step=step)

    def get_items_of_type(
            self,
            item_type: Union[ItemType, Auto],
            verbose: AutoBool = AUTO,
            step: AutoCount = AUTO,
    ) -> Iterable:
        item_type = arg.acquire(item_type, self.get_default_item_type())
        verbose = arg.acquire(verbose, self.is_verbose())
        content_format = self.get_content_format()
        assert isinstance(content_format, ParsedFormat)
        count = self.get_count(allow_slow_gzip=False)
        if isinstance(verbose, str):
            self.log(verbose, verbose=bool(verbose))
        elif (count or 0) > 0:
            self.log('Expecting {} lines in file {}...'.format(count, self.get_name()), verbose=verbose)
        lines = self.get_lines(verbose=verbose, skip_first=self.is_first_line_title(), step=step)
        items = content_format.get_items_from_lines(lines, item_type=item_type)
        return items

    def get_chunks(self, chunk_size=CHUNK_SIZE) -> Iterable:
        return iter(lambda: self.get_fileholder().read(chunk_size), '')

    # def write_lines(self, lines: Iterable, verbose: AutoBool = AUTO, step: AutoCount = AUTO) -> Native:
    def write_lines(self, lines: Iterable, verbose: AutoBool = AUTO) -> Native:
        verbose = arg.acquire(verbose, self.is_verbose())
        ending = self.get_ending().encode(self.get_encoding()) if self.is_gzip() else self.get_ending()
        self.open('w', allow_reopen=True)
        n = 0
        for n, i in enumerate(lines):
            if n > 0:
                self.get_fileholder().write(ending)
            line = str(i).encode(self.get_encoding()) if self.is_gzip() else str(i)
            self.get_fileholder().write(line)
        self.close()
        count = n + 1
        self.set_count(count)
        self.log('Done. {} rows has written into {}'.format(count, self.get_name()), verbose=verbose)
        return self

    def write_items(
            self,
            items: Iterable,
            item_type: Union[ItemType, Auto] = AUTO,
            add_title_row: AutoBool = AUTO,
            verbose: AutoBool = AUTO,
    ) -> Native:
        item_type = arg.undefault(item_type, self.get_default_item_type())
        content_format = self.get_content_format()
        assert isinstance(content_format, ParsedFormat)
        lines = content_format.get_lines(items, item_type=item_type, add_title_row=add_title_row)
        return self.write_lines(lines, verbose=verbose)

    def write_stream(
            self,
            stream: IterableStreamInterface,
            add_title_row: AutoBool = AUTO,
            verbose: AutoBool = AUTO,
    ) -> Native:
        if hasattr(stream, 'get_item_type'):
            item_type = stream.get_item_type()
        else:
            item_type = ItemType.detect(stream.get_one_item())
        return self.write_items(stream.get_items(), item_type=item_type, add_title_row=add_title_row, verbose=verbose)

    def from_stream(self, stream: Stream, verbose: bool = True) -> Native:
        return super(StreamFileMixin).from_stream(stream, verbose=verbose)

    def to_stream(self, data: Union[Iterable, Auto, None] = AUTO, **kwargs) -> Stream:
        if 'stream_type' not in kwargs:
            kwargs['stream_type'] = self.get_stream_type()
        if arg.is_defined(data):
            kwargs['data'] = data
        ex = kwargs.pop('ex', None)
        assert not ex, 'ex-argument for LocalFile.to_stream() not supported (got {})'.format(ex)
        return self.to_stream_type(**kwargs)

    def copy(self) -> Native:
        copy = self.make_new()
        copy.set_declared_format(self.get_declared_format().copy())
        copy.set_detected_format(self.get_detected_format().copy())
        return self._assume_native(copy)
