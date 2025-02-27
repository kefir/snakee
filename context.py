from typing import Optional, Iterable, Union, Any
import gc

try:  # Assume we're a submodule in a package.
    from utils.decorators import singleton
    from interfaces import (
        Context, ContextInterface, Connector, ConnType, Stream, ItemType,
        TemporaryLocationInterface, LoggerInterface, ExtendedLoggerInterface, SelectionLoggerInterface, LoggingLevel,
        Name, ARRAY_TYPES,
    )
    from base.constants.text import DEFAULT_ENCODING
    from base.functions.arguments import get_names, get_generated_name
    from base import base_classes as bs
    from streams import stream_classes as sm
    from connectors import connector_classes as ct
    from connectors.filesystem.temporary_files import TemporaryLocation
    from loggers import logger_classes as lg
    from content.documents import document_classes as dc
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from .utils.decorators import singleton
    from .interfaces import (
        Context, ContextInterface, Connector, ConnType, Stream, ItemType,
        TemporaryLocationInterface, LoggerInterface, ExtendedLoggerInterface, SelectionLoggerInterface, LoggingLevel,
        Name, ARRAY_TYPES,
    )
    from .base.constants.text import DEFAULT_ENCODING
    from .base.functions.arguments import get_names, get_generated_name
    from .base import base_classes as bs
    from .streams import stream_classes as sm
    from .connectors import connector_classes as ct
    from .connectors.filesystem.temporary_files import TemporaryLocation
    from .loggers import logger_classes as lg
    from .content.documents import document_classes as dc

Logger = Union[LoggerInterface, ExtendedLoggerInterface]
Child = Union[Logger, Connector, Stream]
ChildType = Union[ConnType, Child, Name]

NAME = 'cx'
DEFAULT_STREAM_CONFIG = dict(
    max_items_in_memory=sm.MAX_ITEMS_IN_MEMORY,
    tmp_files_template=sm.TMP_FILES_TEMPLATE,
    tmp_files_encoding=DEFAULT_ENCODING,
)
DEFAULT_CONN_CONFIG = dict()


@singleton
class SnakeeContext(bs.AbstractNamed, ContextInterface):
    def __init__(
            self,
            name: Optional[Name] = None,
            stream_config: Optional[dict] = None,
            conn_config: Optional[dict] = None,
            logger: Optional[Logger] = None,
            clear_tmp: bool = False,
    ):
        if name is None:
            name = NAME
        if stream_config is None:
            stream_config = DEFAULT_STREAM_CONFIG
        if conn_config is None:
            conn_config = DEFAULT_CONN_CONFIG
        self.logger = logger
        self.stream_config = stream_config
        self.conn_config = conn_config
        self.stream_instances = dict()
        self.conn_instances = dict()

        super().__init__(name)

        self.sm = sm
        self.sm.set_context(self)
        self.ct = ct
        self.ct.set_context(self)
        self.dc = dc

        if clear_tmp:
            self.clear_tmp_files()

    def set_logger(self, logger: Logger, inplace: bool = False) -> Context:
        self.logger = logger
        if hasattr(logger, 'get_context'):
            if not logger.get_context():
                if hasattr(logger, 'set_context'):
                    logger.set_context(self)
        if not inplace:
            return self

    def get_logger(self, create_if_not_yet: bool = True) -> Optional[Logger]:
        logger = self.logger
        if logger is not None:
            if hasattr(logger, 'get_context') and hasattr(logger, 'set_context'):
                if not logger.get_context():
                    logger.set_context(self)
            return logger
        elif create_if_not_yet:
            logger = lg.get_logger(context=self)
            self.set_logger(logger, inplace=True)
            return logger

    @staticmethod
    def get_new_selection_logger(name: Name, **kwargs) -> lg.SelectionLoggerInterface:
        return lg.SelectionMessageCollector(name, **kwargs)

    def get_selection_logger(self, name: Optional[Name] = None, **kwargs) -> SelectionLoggerInterface:
        logger = self.get_logger()
        if hasattr(logger, 'get_selection_logger'):
            selection_logger = logger.get_selection_logger(name=name, **kwargs)
        else:
            selection_logger = None
        if not selection_logger:
            selection_logger = self.get_new_selection_logger(name=name, **kwargs)
            if hasattr(logger, 'set_selection_logger'):
                logger.set_selection_logger(selection_logger)
        return selection_logger

    def log(
            self,
            msg: str,
            level: Optional[LoggingLevel] = None,
            stacklevel: Optional[int] = None,
            end: Optional[str] = None,
            verbose: bool = True,
    ) -> None:
        logger = self.get_logger()
        if logger is not None:
            logger.log(
                msg=msg, level=level,
                stacklevel=stacklevel,
                end=end, verbose=verbose,
            )

    def set_parent(self, parent: Any, reset: bool = False, inplace: bool = False) -> Context:
        assert not reset, 'SnakeeContext is a root object'
        if not inplace:
            return self

    def set_context(self, context: Context, reset: bool = False, inplace: bool = True) -> Context:
        assert not reset, 'SnakeeContext is a root object'
        if not inplace:
            return self

    def get_items(self) -> Iterable:
        yield from self.conn_instances.items()
        yield from self.stream_instances.items()

    def get_children(self) -> dict:
        return dict(self.get_items())

    def add_child(self, instance: Child, reset: bool = False, inplace: bool = False) -> Context:
        name = instance.get_name()
        err_msg = 'instance with name {} already registered (got {})'
        if ct.is_conn(instance):
            assert reset or name not in self.conn_instances, err_msg.format(name, instance)
            self.conn_instances[name] = instance
        elif sm.is_stream(instance):
            assert reset or name not in self.stream_instances, err_msg.format(name, instance)
            self.stream_instances[name] = instance
        elif lg.is_logger(instance):
            assert isinstance(instance, lg.LoggerInterface)
            if hasattr(instance, 'is_common_logger'):
                if instance.is_common_logger():
                    self.set_logger(instance)
        elif hasattr(instance, 'is_progress'):
            pass
        else:
            raise TypeError("class {} isn't supported by context".format(instance.__class__.__name__))
        if not instance.get_context():
            instance.set_context(self)
        if not inplace:
            return self

    def conn(
            self,
            conn: Union[Connector, ChildType],
            name: Optional[Name] = None,
            check: bool = True,
            redefine: bool = True,
            **kwargs
    ) -> Connector:
        if name is None:
            name = get_generated_name('Connection')
        conn_object = self.conn_instances.get(name)
        if conn_object:
            if redefine or ct.is_conn(conn):
                self.forget_conn(name, verbose=False)
            else:
                return conn_object
        if ct.is_conn(conn):
            conn_object = conn
        else:
            conn_class = ct.get_class(conn)
            try:
                if conn_class == ct.LocalFolder or hasattr(conn_class, 'get_default_storage'):  # TMP workaround fix
                    if name is not None and 'path' not in kwargs:
                        kwargs['path'] = name
                    conn_object = conn_class(context=self, **kwargs)  # TMP workaround fix
                else:
                    conn_object = conn_class(context=self, name=name, **kwargs)
            except TypeError as e:
                raise TypeError(f'{conn}: {e}')
        self.conn_instances[name] = conn_object
        if check and hasattr(conn_object, 'check'):
            conn_object.check()
        return conn_object

    def stream(
            self,
            data: Iterable,
            item_type: Union[ItemType, Stream],
            name: Optional[Name] = None,
            check: bool = True,
            **kwargs
    ) -> Stream:
        if name is not None:
            name = get_generated_name('Stream')
        if isinstance(item_type, Stream) or sm.is_stream(item_type):
            stream_object = item_type
        else:
            stream_object = sm.StreamBuilder.stream(data, item_type, **kwargs)
        stream_object = stream_object.set_name(
            name,
            register=False,
        ).fill_meta(
            context=self,
            check=check,
            **self.stream_config
        )
        self.stream_instances[name] = stream_object
        return stream_object

    def get_stream(self, name: Name, skip_missing: bool = True) -> Optional[Stream]:
        if skip_missing:
            return self.stream_instances.get(name)
        else:
            return self.stream_instances[name]

    def get_connection(self, name: Name, skip_missing: bool = True) -> Connector:
        if skip_missing:
            return self.conn_instances.get(name)
        else:
            return self.conn_instances[name]

    def get_child(self, name: Name, class_or_type: ChildType = None, deep: bool = True) -> Child:
        if 'Stream' in str(class_or_type):
            return self.get_stream(name)
        elif 'Conn' in str(class_or_type):
            return self.get_connection(name)
        elif 'Logger' in str(class_or_type):
            return self.get_logger()
        elif class_or_type is None:
            if name in self.stream_instances:
                return self.stream_instances[name]
            elif name in self.conn_instances:
                return self.conn_instances[name]
            elif deep:
                for c in self.conn_instances:
                    if hasattr(c, 'get_children'):
                        return c.get_children().get(name)

    def _get_name_and_child(self, name_or_child: Union[Name, Child]) -> tuple:
        if isinstance(name_or_child, (str, int)):
            name = name_or_child
            child = self.get_child(name)
        else:
            child = name_or_child
            assert hasattr(child, 'get_name'), 'DataWrapper expected, got {}'.format(type(child))
            name = child.get_name()
        return name, child

    def rename_stream(self, old_name: Name, new_name: Name, inplace: bool = True) -> Union[Stream, ContextInterface]:
        assert old_name in self.stream_instances, 'Stream must be defined (name {} is not registered)'.format(old_name)
        if new_name != old_name:
            assert new_name not in self.stream_instances, 'Stream name "{}" already exists'.format(new_name)
            stream = self.stream_instances.pop(old_name)
            self.stream_instances[new_name] = stream
        else:
            stream = self.stream_instances[new_name]
        if inplace:
            return self
        else:
            return stream

    def take_credentials_from_file(self, file: Union[Name, Connector]) -> ContextInterface:
        for name, conn in self.get_children().items():
            if hasattr(conn, 'take_credentials_from_file'):
                conn.take_credentials_from_file(file=file, by_name=True)
        return self

    def get_local_storage(self, name: Name = 'filesystem', create_if_not_yet: bool = True) -> Connector:
        local_storage = self.conn_instances.get(name)
        if local_storage:
            assert isinstance(local_storage, ct.LocalStorage)
        elif create_if_not_yet:
            local_storage = ct.LocalStorage(name, context=self)
        if local_storage:
            self.conn_instances[name] = local_storage
        return local_storage

    def get_job_folder(self, instance_name: Name = 'job', config_field_name: str = 'job_folder') -> Connector:
        job_folder_obj = self.conn_instances.get(instance_name)
        if job_folder_obj:
            return job_folder_obj
        else:
            job_folder_path = self.stream_config.get(config_field_name, '')
            job_folder_obj = ct.LocalFolder(job_folder_path, parent=self.get_local_storage(), context=self)
            self.conn_instances[instance_name] = job_folder_obj
            return job_folder_obj

    def find_job_folder(self, required_folders: Iterable, max_depth: int = 5) -> Connector:
        if isinstance(required_folders, str):
            set_required_folders = {required_folders}
        else:
            set_required_folders = set(get_names(required_folders))
        current_folder = self.get_job_folder()
        for depth in range(max_depth):
            assert isinstance(current_folder, ct.LocalFolder) or hasattr(current_folder, 'get_existing_folder_names')
            set_existing_folders = set(current_folder.get_existing_folder_names())
            if set_existing_folders >= set_required_folders:
                return current_folder
            else:
                current_folder = current_folder.get_parent_folder()
        raise FileNotFoundError(f'find_job_folder(): job-folder with required_folders={required_folders} not found')

    def get_tmp_folder(
            self,
            instance_name: Name = 'tmp',
            config_field_name: str = 'tmp_files_template',
    ) -> TemporaryLocationInterface:
        tmp_folder = self.conn_instances.get(instance_name)
        if tmp_folder:
            return tmp_folder
        else:
            tmp_folder = TemporaryLocation(parent=self.get_local_storage())
            return tmp_folder

    def clear_tmp_files(self, verbose: bool = True) -> int:
        return self.get_tmp_folder().clear_all(forget=True, verbose=verbose)

    def close_conn(self, name: Name, recursively: bool = False, verbose: bool = True) -> int:
        closed_count = 0
        this_conn = self.conn_instances[name]
        closed_count += this_conn.close() or 0
        if recursively and hasattr(this_conn, 'get_links'):
            for link in this_conn.get_links():
                if hasattr(link, 'close'):
                    closed_count += link.close() or 0
        if verbose and closed_count:
            self.log('{} connection(s) closed.'.format(closed_count))
        return closed_count

    def close_stream(self, name: Name, recursively: bool = False, verbose: bool = True) -> tuple:
        this_stream = self.get_stream(name, skip_missing=False)
        closed = 0
        if isinstance(this_stream, sm.IterableStream) or hasattr(this_stream, 'close'):
            closed = this_stream.close() or 0
        if isinstance(closed, ARRAY_TYPES):
            closed_stream, closed_links = closed[:2]
        else:  # isinstance(closed, int):
            closed_stream, closed_links = closed, 0
        if recursively and hasattr(this_stream, 'get_links'):
            for link in this_stream.get_links():
                if not link == self:
                    closed_links += link.close() or 0
        if verbose:
            self.log('{} stream(es) and {} link(s) closed.'.format(closed_stream, closed_links))
        else:
            return closed_stream, closed_links

    def close_all_conns(self, recursively: bool = False, verbose: bool = True) -> int:
        closed_count = 0
        for name in self.conn_instances:
            closed_count += self.close_conn(name, recursively=recursively, verbose=False)
        if verbose and closed_count:
            self.log('{} connection(s) closed.'.format(closed_count))
        return closed_count

    def close_all_streams(self, recursively: bool = False, verbose: bool = True) -> tuple:
        closed_streams, closed_links = 0, 0
        for name in self.stream_instances:
            closed = self.close_stream(name, recursively=recursively, verbose=False)
            if isinstance(closed, ARRAY_TYPES):
                closed_streams += closed[0]
                closed_links += closed[1]
            elif isinstance(closed, int):
                closed_streams += closed
        if verbose:
            self.log('{} stream(es) and {} link(s) closed.'.format(closed_streams, closed_links))
        return closed_streams, closed_links

    def close(self, verbose: bool = True) -> tuple:
        closed_conns = self.close_all_conns(recursively=True, verbose=False)
        closed_streams, closed_links = self.close_all_streams(recursively=True, verbose=False)
        if verbose:
            self.log('{} conn(s), {} stream(es), {} link(s) closed.'.format(closed_conns, closed_streams, closed_links))
        return closed_conns, closed_streams, closed_links

    def forget_conn(self, conn: Union[Name, Connector], recursively=True, skip_errors=False, verbose=True) -> int:
        name, conn = self._get_name_and_child(conn)
        if name in self.conn_instances:
            self.close_conn(name, recursively=recursively, verbose=verbose)
            conn = self.conn_instances.pop(name)
            count = 1
            if recursively and hasattr(conn, 'forget_all_children'):
                count += conn.forget_all_children()
            gc.collect()
            return count
        elif not skip_errors:
            raise TypeError('connection {} with name {} not registered'.format(conn, name))

    def forget_stream(self, stream: Union[Name, Stream], recursively=True, skip_errors=False, verbose=True) -> int:
        name, stream = self._get_name_and_child(stream)
        if name in self.stream_instances:
            self.close_stream(name, recursively=recursively, verbose=verbose)
            self.stream_instances.pop(name)
            gc.collect()
            return 1
        elif not skip_errors:
            raise TypeError('stream {} with name {} not registered'.format(stream, name))

    def forget_child(self, name_or_child: Union[Name, Child], recursively=True, skip_errors=False) -> int:
        name, child = self._get_name_and_child(name_or_child)
        count = 0
        if name in self.conn_instances:
            count += self.forget_conn(name, recursively=recursively, skip_errors=skip_errors) or 0
        if name in self.stream_instances:
            count += self.forget_stream(name, recursively=recursively, skip_errors=skip_errors) or 0
        return count

    def forget_all_conns(self, recursively: bool = False, verbose: bool = True) -> int:
        closed_count = self.close_all_conns(verbose=False)
        left_count = 0
        for name in list(self.conn_instances):
            left_count += self.forget_conn(name, recursively=recursively, verbose=False)
        self.conn_instances = dict()
        self.log('{} connection(s) closed, {} connection(s) left.'.format(closed_count, left_count), verbose=verbose)
        return left_count

    def forget_all_streams(self, recursively: bool = False, verbose: bool = True) -> int:
        closed_streams, closed_links = self.close_all_streams(verbose=False)
        left_count = 0
        for name in self.stream_instances.copy():
            left_count += self.forget_stream(name, recursively=recursively, verbose=False)
        message = '{} stream(s) and {} link(s) closed, {} stream(es) left'
        self.log(message.format(closed_streams, closed_links, left_count), verbose=verbose)
        return left_count

    def forget_all_children(self, verbose: bool = True) -> int:
        count = 0
        self.close(verbose=True)
        count += self.forget_all_conns(recursively=True, verbose=verbose) or 0
        count += self.forget_all_streams(recursively=True, verbose=verbose) or 0
        return count

    def __repr__(self):
        return NAME
