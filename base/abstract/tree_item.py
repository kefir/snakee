from typing import Union, Optional, Iterable

try:  # Assume we're a sub-module in a package.
    from utils import arguments as arg
    from base.interfaces.tree_interface import TreeInterface
    from base.interfaces.context_interface import ContextInterface
    from base.abstract.abstract_base import AbstractBaseObject
    from base.abstract.contextual import Contextual
    from base.abstract.data import DataWrapper
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...utils import arguments as arg
    from ..interfaces.tree_interface import TreeInterface
    from ..interfaces.context_interface import ContextInterface
    from .abstract_base import AbstractBaseObject
    from .contextual import Contextual
    from .data import DataWrapper

Context = Optional[ContextInterface]
Parent = Union[Context, TreeInterface]
Child = Optional[DataWrapper]
NameOrChild = Union[str, DataWrapper]
OptionalFields = Optional[Union[str, Iterable]]

META_MEMBER_MAPPING = dict(_data='children', _source='parent')


class TreeItem(DataWrapper, TreeInterface):
    def __init__(
            self,
            name: str,
            parent: Parent = None,
            children: Optional[dict] = None,
            context: Context = None,
    ):
        if not children:
            children = dict()
        super().__init__(name=name, data=children, source=parent, context=context)

    @classmethod
    def _get_meta_member_mapping(cls) -> dict:
        meta_member_mapping = super()._get_meta_member_mapping()
        meta_member_mapping.update(META_MEMBER_MAPPING)
        return meta_member_mapping

    def get_parent(self) -> Parent:
        return super().get_source()

    def set_parent(self, parent: Parent, reset=False, inplace=True) -> Optional[TreeInterface]:
        assert isinstance(parent, TreeInterface)
        return self.set_source(parent, reset=reset, inplace=inplace)

    def get_children(self) -> dict:
        return super().get_data()

    def get_child(self, name: str) -> Child:
        return self.get_children().get(name)

    def _get_name_and_child(self, name_or_child: NameOrChild) -> tuple:
        if isinstance(name_or_child, str):
            name = name_or_child
            child = self.get_context().get_child(name)
        else:
            child = name_or_child
            assert isinstance(child, DataWrapper), 'DataWrapper expected (got {} as {})'.format(
                child, type.__class__.__name__,
            )
            name = child.get_name()
        return name, child

    def add_child(self, name_or_child: NameOrChild):
        children = self.get_children()
        name, child = self._get_name_and_child(name_or_child)
        if name in children:
            if self.get_child(name) != child:
                raise ValueError('child with name {} already registered in {}'.format(name, self.__repr__()))
        children[name] = name_or_child
        if hasattr(child, 'set_parent'):
            child.set_parent(self)

    def get_items(self) -> Iterable:
        yield from self.get_children().values()

    def close(self) -> int:
        count = 0
        for child in self.get_children().values():
            if hasattr(child, 'close'):
                count += child.close()
        return count

    def forget_child(self, name_or_child: NameOrChild, recursively=False, skip_errors=False) -> int:
        name, child = self._get_name_and_child(name_or_child)
        if name in self.get_children() or skip_errors:
            child = self.get_children().pop(name)
            if child:
                child.close()
                count = 1
                if recursively:
                    for c in child.get_children():
                        count += c.forget_all_children()
                return count
        else:
            raise TypeError('child {} with name {} not registered'.format(name, child))

    def forget_all_children(self) -> int:
        count = 0
        for name in self.get_children():
            count += self.forget_child(name)
        return count

    def get_data(self) -> Iterable:
        for _, i in self.get_children():
            if hasattr(i, 'get_data'):
                yield from i.get_data()

    def close_child(self, name_or_child) -> int:
        child = self.get_child(name_or_child)
        return child.close()

    def has_children(self) -> bool:
        return bool(self.get_children())

    def is_leaf(self) -> bool:
        return not self.has_children()

    def is_root(self) -> bool:
        parent = self.get_parent()
        if parent:
            if not parent.is_context():
                return False
        return True

    @staticmethod
    def is_context() -> bool:
        return False

    def get_context(self) -> Parent:
        parent = self.get_parent()
        if parent:
            if parent.is_context():
                return parent
            else:
                return parent.get_context()

    def get_breadcrumbs(self):
        if self.is_root():
            hierarchy = list()
        else:
            hierarchy = self.get_parent().get_names_hierarchy()
        return hierarchy + [self.get_name()]

    def _get_meta_args(self) -> list:
        meta_args = super()._get_meta_args()
        meta_args.pop(1)
        return meta_args

    def __str__(self):
        str_repr = '{}({})'.format(self.__class__.__name__, self.get_str_meta())
        obj = self
        while obj.get_parent():
            obj = obj.get_parent()
            str_repr = '{}.{}'.format(obj.__repr__(), str_repr)
        return '<{}>'.format(str_repr)
