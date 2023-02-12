from typing import Optional, Iterable, Iterator, Generator, Sequence, Union

try:  # Assume we're a submodule in a package.
    from interfaces import Item, ItemType, ContentType, Class, Count, Auto
    from base.constants.chars import PARAGRAPH_CHAR, SPACE, HTML_SPACE, SHARP
    from base.classes.display import DisplayInterface, DefaultDisplay
    from base.mixin.display_mixin import DisplayMixin, Class
    from utils.external import display, clear_output, Markdown, HTML
    from utils.decorators import deprecated_with_alternative
    from content.format.text_format import TextFormat, Compress, DEFAULT_ENCODING
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...interfaces import Item, ItemType, ContentType, Class, Count, Auto
    from ...base.constants.chars import PARAGRAPH_CHAR, SPACE, HTML_SPACE, SHARP
    from ...base.classes.display import DisplayInterface, DefaultDisplay
    from ...base.mixin.display_mixin import DisplayMixin, Class
    from ...utils.external import display, clear_output, Markdown, HTML
    from ...utils.decorators import deprecated_with_alternative
    from .text_format import TextFormat, Compress, DEFAULT_ENCODING

Native = Union[DefaultDisplay, TextFormat]
Style = Optional[str]
FormattedDisplayTypes = Union[Markdown, HTML]
DisplayObject = Union[FormattedDisplayTypes, str]
Paragraph = Union[str, Iterable, None]

H_STYLE = None
P_STYLE = 'line-height: 1.1em; margin-top: 0em; margin-bottom: 0em; padding-top: 0em; padding-bottom: 0em;'


class DocumentFormat(TextFormat):
    def __init__(
            self,
            ending: str = PARAGRAPH_CHAR,  # '\n'
            encoding: str = DEFAULT_ENCODING,  # 'utf8'
            compress: Compress = None,
    ):
        super().__init__(ending=ending, encoding=encoding, compress=compress)

    def get_encoded_paragraph(
            self,
            paragraph: Paragraph = None,
            level: Count = None,
            style: Style = None,
            clear: bool = True,  # deprecated
    ) -> Iterator[str]:
        if clear:  # by default
            self.clear_current_paragraph()
        yield from super().get_encoded_paragraph(paragraph)

    @staticmethod
    def _get_display_class() -> Class:
        return str

    @classmethod
    def _get_display_object(cls, data: Union[str, Iterable, None]) -> Optional[DisplayObject]:
        if not data:
            return None
        if hasattr(data, 'get_lines'):
            data = data.get_lines()
        if isinstance(data, Iterable) and not isinstance(data, str):
            data = PARAGRAPH_CHAR.join(data)
        display_class = cls._get_display_class()
        if display_class:
            return display_class(data)
        else:
            return str(data)


class MarkdownFormat(DocumentFormat):
    @staticmethod
    def _get_display_class():
        return Markdown

    def get_encoded_paragraph(
            self,
            paragraph: Paragraph = None,
            level: Count = None,
            clear: bool = True,  # deprecated
            style: Style = None,
    ) -> Iterator[str]:
        paragraph = super().get_encoded_paragraph(paragraph, clear=clear)
        yield from self.get_md_text_code(paragraph, level=level)

    @staticmethod
    def get_md_text_code(lines: Iterable[str], level: Optional[int] = None) -> Iterator[str]:
        text = PARAGRAPH_CHAR.join(lines)
        if level:
            prefix = SHARP * level
            yield f'{prefix} {text}'
        else:
            yield text


class HtmlFormat(DocumentFormat):
    @staticmethod
    def _get_display_class():
        return HTML

    def get_encoded_paragraph(
            self,
            paragraph: Paragraph = None,
            level: Optional[int] = None,
            clear: bool = True,  # deprecated
            style: Style = None,
    ) -> Iterator[str]:
        paragraph = super().get_encoded_paragraph(paragraph, clear=clear)
        for html_string in self.get_html_text_code(paragraph, level=level, style=style):
            yield html_string.replace(SPACE * 2, HTML_SPACE * 2)

    def get_encoded_sheet(
            self,
            records: Iterable,
            columns: Iterable,
            count: Count,
            with_title: bool,
            style: Style = None,
    ) -> Iterator[str]:
        columns = list(self._get_column_names(columns))
        html_code_lines = self.get_html_table_code(records, columns, count, with_title, style=style)
        return map(lambda i: i.replace(SPACE * 2, HTML_SPACE * 2), html_code_lines)

    @staticmethod
    def get_html_text_code(
            lines: Iterable[str],
            level: Optional[int] = None,
            style: Style = None,
    ) -> Iterator[str]:
        if isinstance(lines, str):
            lines = lines.split(PARAGRAPH_CHAR)
        assert isinstance(lines, Iterable), f'got {lines}'
        delimiter = '{tag}{char}'.format(tag='<br>', char=PARAGRAPH_CHAR)
        text = delimiter.join(lines)
        if level:
            tag = f'h{level}'
            if not Auto.is_defined(style):
                style = H_STYLE
        else:
            tag = 'p'
            if not Auto.is_defined(style):
                style = P_STYLE
        open_tag = f'<{tag} style="{style}">' if style else f'<{tag}>'
        close_tag = f'</{tag}>'
        if text:
            yield f'{open_tag}{text}{close_tag}'

    @staticmethod
    def get_html_table_code(
            records: Iterable,
            columns: Sequence,
            count: Count = None,
            with_title: bool = True,
            style: str = None,
    ) -> Generator:
        yield '<table>'
        if with_title:
            yield '<thead>'
            yield '<tr>'
            for c in columns:
                yield f'<th>{c}</th>'
            yield '</tr>'
        yield '</thead>'
        yield '<tbody>'
        for n, r in list(enumerate(records)):
            if Auto.is_defined(count):
                if n >= count:
                    break
            yield '<tr>'
            for col in columns:
                value = r.get(col)
                if Auto.is_defined(style):
                    yield f'<td>{value}</td>'
                else:
                    yield f'<td style="{style}">{value}</td>'
            yield '</tr>'
        yield '</tbody>'
        yield '</table>'

    def clear_output(self):
        self.display_paragraph()
        clear_output()
