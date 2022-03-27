from abc import ABC, abstractmethod
from typing import Optional, Callable, Generator, Union

try:  # Assume we're a submodule in a package.
    from interfaces import (
        TermInterface, FieldInterface,
        TermType, TermDataAttribute, TermRelation, FieldRoleType, FieldType,
        AUTO, Auto, AutoCount,
    )
    from base.functions.arguments import get_name, get_names, get_value
    from base.constants.chars import EMPTY, UNDER, SMALL_INDENT, REPR_DELIMITER, JUPYTER_LINE_LEN
    from base.abstract.simple_data import SimpleDataWrapper
    from base.classes.enum import ClassType
    from content.fields.advanced_field import AdvancedField
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...interfaces import (
        TermInterface, FieldInterface,
        TermType, TermDataAttribute, TermRelation, FieldRoleType, FieldType,
        AUTO, Auto, AutoCount,
    )
    from ...base.functions.arguments import get_name, get_names, get_value
    from ...base.constants.chars import EMPTY, UNDER, SMALL_INDENT, REPR_DELIMITER, JUPYTER_LINE_LEN
    from ...base.abstract.simple_data import SimpleDataWrapper
    from ...base.classes.enum import ClassType
    from ..fields.advanced_field import AdvancedField

Native = SimpleDataWrapper
Field = Union[FieldInterface, str]
RoleType = FieldRoleType  # deprecated

FIELD_ROLES_WITHOUT_SUFFIXES = FieldRoleType.Repr, FieldRoleType.Value, FieldRoleType.Undefined
FIELD_NAME_TEMPLATE = '{term}' + UNDER + '{role}'
FIELD_CAPTION_TEMPLATE = '{role} of {term} ({caption})'
DESCRIPTION_COLUMN_LENS = 3, 10, 20, 85  # prefix, key, value, caption


class AbstractTerm(SimpleDataWrapper, TermInterface, ABC):
    def __init__(
            self,
            name: str,
            caption: str = EMPTY,
            fields: Optional[dict] = None,
            mappers: Optional[dict] = None,
            datasets: Optional[dict] = None,
            relations: Optional[dict] = None,
            data: Optional[dict] = None,
    ):
        assert name, 'AbstractTerm: name must be non-empty'
        self._caption = caption
        super().__init__(name=name, data=data or dict())
        self.add_fields(fields)
        self.add_mappers(mappers)
        self.add_datasets(datasets)
        self.add_relations(relations)

    @abstractmethod
    def get_term_type(self) -> TermType:
        pass

    def get_type(self) -> TermType:
        return self.get_term_type()

    def get_caption(self) -> str:
        return self._caption

    def add_to_data(self, key: Union[TermDataAttribute, str], value: Optional[dict] = None, **kwargs) -> Native:
        if not (value or kwargs):
            return self
        if not isinstance(key, TermDataAttribute):
            key = TermDataAttribute(key)
        data = self.get_data()
        assert isinstance(data, dict), 'AbstractTerm.add_to_data(): Expected data as dict, got {}'.format(data)
        if key not in data:
            data[key] = dict()
        data_dict = data[key]
        assert isinstance(data_dict, dict), 'AbstractTerm.add_to_data(): Expected data as dict, got {}'.format(data)
        added_items = list()
        if value:
            added_items += list(value.items())
        added_items += list(kwargs.items())
        if isinstance(key, ClassType) or hasattr(key, 'get_class'):
            subkey_class = key.get_class()
        else:
            subkey_class = str
        for k, v in added_items:
            if isinstance(k, str) and subkey_class != str:
                k = subkey_class(k)
            data_dict[k] = v
        return self

    def get_from_data(self, key: Union[TermDataAttribute], subkey=None) -> dict:
        data = self.get_data()
        assert isinstance(data, dict), 'AbstractTerm.get_from_data(): Expected data as dict, got {}'.format(data)
        if key not in data:
            data[key] = dict()
        if subkey is None:
            return data[key]
        else:
            return data[key].get(subkey)

    def add_field(self, field: AdvancedField, role: FieldRoleType) -> Native:
        return self.add_fields({role: field})

    def add_fields(self, value: Optional[dict] = None, **kwargs) -> Native:
        return self.add_to_data(TermDataAttribute.Fields, value=value, **kwargs)

    def add_mappers(self, value: Optional[dict] = None, **kwargs) -> Native:
        return self.add_to_data(TermDataAttribute.Mappers, value=value, **kwargs)

    def add_datasets(self, value: Optional[dict] = None, **kwargs) -> Native:
        return self.add_to_data(TermDataAttribute.Datasets, value=value, **kwargs)

    def add_relations(self, value: Optional[dict] = None, update_relations: bool = True, **kwargs) -> Native:
        self.add_to_data(TermDataAttribute.Relations, value=value, **kwargs)
        return self.update_relations() if update_relations else self

    def update_relations(self) -> Native:
        relations = self.get_from_data(TermDataAttribute.Relations)
        for k, v in relations.items():
            assert isinstance(k, AbstractTerm), 'update_relations(): expected AbstractTerm, got {}'.format(k)
            assert isinstance(v, TermRelation), 'update_relations(): expected TermRelation, got {}'.format(v)
            reversed_relation = v.get_reversed()
            k.add_relations({self: reversed_relation}, update_relations=False)
        return self

    def get_item(self, key: TermDataAttribute, subkey, skip_missing: Union[bool, Auto] = AUTO, default=None):
        skip_missing = Auto.acquire(skip_missing, default is not None)
        data_dict = self.get_from_data(key)
        if subkey in data_dict:
            return data_dict[subkey]
        elif skip_missing:
            return default
        else:
            formatter = '{cls}.get_item({key}, {subkey}): item {subkey} not exists: {existing}'
            msg = formatter.format(cls=self.__class__.__name__, key=key, subkey=subkey)
            raise IndexError(msg)

    def add_item(self, key: TermDataAttribute, subkey, value, allow_override: bool = False) -> Native:
        data_dict = self.get_from_data(key)
        if not allow_override:
            if subkey in data_dict:
                existing = data_dict[subkey]
                formatter = '{cls}.add_item({key}, {subkey}, {value}): item {subkey} already exists: {existing}'
                cls = self.__class__.__name__
                msg = formatter.format(cls=cls, key=key, subkey=subkey, value=value, existing=existing)
                raise ValueError(msg)
        data_dict[subkey] = value
        return self

    def field(
            self,
            name: str,
            value_type: Union[FieldType, Auto] = AUTO,
            role: Union[FieldRoleType, str, Auto] = AUTO,
            caption: Union[str, Auto] = AUTO,
            **kwargs
    ) -> FieldInterface:
        if Auto.is_auto(role):
            suffix = name.split(UNDER)[-1]
            role = FieldRoleType.detect(suffix, default=FieldRoleType.Undefined)
        return self.get_field_by_role(role, value_type=value_type, name=name, caption=caption, **kwargs)

    def get_fields_by_roles(self) -> dict:
        return self.get_from_data(TermDataAttribute.Fields)

    def get_field_by_role(
            self,
            role: FieldRoleType,
            value_type: Union[FieldType, Auto] = AUTO,
            name: Union[str, Auto] = AUTO,
            caption: Union[str, Auto] = AUTO,
            **kwargs
    ) -> Field:
        fields_by_roles = self.get_fields_by_roles()
        role_value = get_value(role)
        if role_value in fields_by_roles:
            field = fields_by_roles[role_value]
            if kwargs:
                assert isinstance(field, AdvancedField)
                field = field.set_outplace(**kwargs)
        else:
            field_class = self._get_default_field_class_by_role(role)
            field_name = Auto.delayed_acquire(name, self._get_default_field_name_by_role, role)
            value_type = Auto.delayed_acquire(value_type, self._get_default_value_type_by_role, role)
            field_caption = Auto.delayed_acquire(caption, self._get_default_field_caption_by_role, role)
            field = field_class(field_name, value_type, caption=field_caption, **kwargs)
            fields_by_roles[role_value] = field
        return field

    @staticmethod
    def _get_default_field_class():
        return AdvancedField

    def _get_default_field_class_by_role(self, role: FieldRoleType):
        default = self._get_default_field_class()
        if not isinstance(role, FieldRoleType):
            role = FieldRoleType(role)
        custom = role.get_class(default=default)
        if isinstance(custom, FieldInterface):
            return custom
        else:
            return default

    def _get_default_field_name_by_role(self, role: FieldRoleType) -> str:
        term_name = self.get_name()
        if role in FIELD_ROLES_WITHOUT_SUFFIXES or role in (None, AUTO):
            field_name = term_name
        else:
            field_name = FIELD_NAME_TEMPLATE.format(term=term_name, role=get_value(role))
        return field_name

    def _get_default_field_caption_by_role(self, role: FieldRoleType) -> str:
        term_caption = self.get_caption()
        if role in FIELD_ROLES_WITHOUT_SUFFIXES or role in (None, AUTO):
            field_caption = term_caption
        else:
            term_name = self.get_name()
            role_value = get_value(role)
            field_caption = FIELD_CAPTION_TEMPLATE.format(role=role_value, term=term_name, caption=term_caption)
        return field_caption

    @staticmethod
    def _get_default_value_type_by_role(role: FieldRoleType, default_type: FieldType = FieldType.Any) -> FieldType:
        if not isinstance(role, FieldRoleType):
            role = FieldRoleType.detect(role)
        return role.get_default_value_type(default=default_type)

    def add_mapper(self, src: Field, dst: Field, mapper: Callable) -> Native:
        key = TermDataAttribute.Mappers
        subkey = get_names([src, dst])
        assert isinstance(key, TermDataAttribute)
        return self.add_item(key, subkey, mapper)

    def get_mapper(self, src: Field, dst: Field, default: Optional[Callable] = None) -> Optional[Callable]:
        key = TermDataAttribute.Mappers
        subkey = get_names([src, dst])
        assert isinstance(key, TermDataAttribute)
        return self.get_item(key, subkey, skip_missing=True, default=default)

    def get_str_headers(self) -> Generator:
        yield self.get_brief_repr()
        yield self.get_caption()

    def get_meta_description(
            self,
            with_title: bool = True,
            with_summary: bool = True,
            prefix: str = SMALL_INDENT,
            delimiter: str = REPR_DELIMITER,
    ) -> Generator:
        if len(list(self.get_meta_items())) > 2:
            yield from super().get_meta_description(
                with_title=with_title, with_summary=with_summary,
                prefix=prefix, delimiter=delimiter,
            )

    def get_data_description(
            self,
            count: AutoCount = None,
            title: Optional[str] = 'Data:',
            max_len: AutoCount = AUTO,
    ) -> Generator:
        count = Auto.acquire(count, None)
        max_len = Auto.acquire(max_len, JUPYTER_LINE_LEN)
        data_keys = sorted(self.get_data().keys())
        for key in data_keys:
            key_name, value_name = key.get_dict_names()
            column_names = 'prefix', key_name, value_name, 'caption'
            columns = list(zip(column_names, DESCRIPTION_COLUMN_LENS))
            data = self.get_data()[key]
            if data:
                yield '{key}:'.format(key=get_name(key))
                records = map(
                    lambda i: {
                        key_name: get_name(i[0]),
                        value_name: get_name(i[1]),
                        'caption': i[0].get_caption() if hasattr(i[0], 'get_caption') else
                        i[1].get_caption() if hasattr(i[1], 'get_caption') else '',
                    },
                    data.items(),
                )
                yield from self._get_columnar_lines(records, columns=columns, count=count, max_len=max_len)

    # @deprecated
    def get_type_in(self, dialect=None):  # TMP for compatibility with AbstractField/StructInterface
        return list

    def __hash__(self):
        return hash(self.get_name())

    def __repr__(self):
        return self.get_name()
