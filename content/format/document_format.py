from typing import Optional, Callable, Iterable, Iterator, Generator, Sequence, Union

try:  # Assume we're a submodule in a package.
    from interfaces import Item, ItemType, ContentType, AutoCount, Auto, AUTO
    from base.classes.display import DefaultDisplay, PREFIX_FIELD
    from base.mixin.display_mixin import DisplayMixin, AutoOutput, Class
    from utils.external import display, HTML, Markdown
    from utils.decorators import deprecated
    from content.format.text_format import TextFormat, Compress, DEFAULT_ENDING, DEFAULT_ENCODING
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ...interfaces import Item, ItemType, ContentType, AutoCount, Auto, AUTO
    from ...base.classes.display import DefaultDisplay, PREFIX_FIELD
    from ...base.mixin.display_mixin import DisplayMixin, AutoOutput, Class
    from ...utils.external import display, HTML, Markdown
    from ...utils.decorators import deprecated
    from .text_format import TextFormat, Compress, DEFAULT_ENDING, DEFAULT_ENCODING

H_STYLE = None
P_STYLE = 'line-height: 1.1em; margin-top: 0em; margin-bottom: 0em; padding-top: 0em; padding-bottom: 0em;'
SPACE = ' '
HTML_SPACE = '&nbsp;'


class DocumentFormat(TextFormat, DefaultDisplay):
    def __init__(
            self,
            ending: str = DEFAULT_ENDING,
            encoding: str = DEFAULT_ENCODING,
            compress: Compress = None,
    ):
        self._current_paragraph = list()
        super().__init__(ending=ending, encoding=encoding, compress=compress)

    def get_current_paragraph(self) -> Iterable:
        return self._current_paragraph

    def set_current_paragraph(self, paragraph):
        self._current_paragraph = paragraph
        return self

    def clear_current_paragraph(self):
        return self.set_current_paragraph(list())

    def get_encoded_paragraph(
            self,
            paragraph: Optional[Iterable] = None,
            level: Optional[int] = None,
            style=AUTO,
            clear: bool = False,
    ) -> str:
        if paragraph and isinstance(paragraph, str):
            encoded_paragraph = paragraph
        else:
            encoded_paragraph = '\n'.join(self.get_current_paragraph())
            if clear:
                self.clear_current_paragraph()
        return encoded_paragraph

    @staticmethod
    def _get_display_class():
        return str

    @classmethod
    def _get_display_object(cls, data: Union[str, Iterable]) -> str:
        if not isinstance(data, str):
            data = '\n'.join(data)
        display_class = cls._get_display_class()
        if display_class:
            return display_class(data)
        else:
            return str(data)

    def append_to_current_paragraph(self, line: str) -> None:
        self._current_paragraph.append(line)

    @deprecated
    def output_line(self, line: str, output: AutoOutput = AUTO) -> None:
        if line:
            return self.append(line)
        else:
            return self.display_paragraph()

    @deprecated
    def get_output(self, output: AutoOutput = AUTO):
        if Auto.is_auto(output):
            return self._get_display_method()
        else:
            return super().get_output(output=output)

    @staticmethod
    def _get_display_method() -> Callable:
        return display

    def display_paragraph(self, paragraph: Optional[Iterable] = None, level: Optional[int] = None, style=AUTO):
        data = self.get_encoded_paragraph(paragraph, level=level, style=style, clear=True)
        if data:
            obj = self._get_display_object(data)
            return display(obj)

    def display_sheet(
            self,
            records: Iterable,
            columns: Sequence,
            count: AutoCount = None,
            with_title: bool = True,
            style: Union[str, Auto, None] = AUTO,
            output: AutoOutput = AUTO,
    ):
        self.display_paragraph()
        data = self.get_encoded_sheet(records, columns=columns, count=count, with_title=with_title, style=style)
        sheet = self._get_display_object(data)
        return display(sheet)


class MarkdownFormat(DocumentFormat):
    @staticmethod
    def _get_display_class():
        return Markdown

    def get_encoded_paragraph(self, paragraph: Optional[Iterable] = None, level: Optional[int] = None, clear: bool = False) -> str:
        data = super().get_encoded_paragraph(paragraph)
        return self.get_md_text_code(data, level=level)

    @staticmethod
    def get_md_text_code(text: str, level: Optional[int] = None) -> str:
        if level:
            prefix = '#' * level
            return f'{prefix} {text}'
        else:
            return text


class HtmlFormat(DocumentFormat):
    @staticmethod
    def _get_display_class():
        return HTML

    def get_encoded_paragraph(self, paragraph=None, level: Optional[int] = None, clear: bool = False, style=AUTO) -> str:
        paragraph = super().get_encoded_paragraph(paragraph, clear=clear)
        if paragraph:
            html_code = self.get_html_text_code(paragraph, level=level, style=style)
            return html_code.replace(SPACE * 2, HTML_SPACE * 2)
        else:
            return ''

    def get_encoded_sheet(self, records, columns, count, with_title, style=AUTO) -> Iterator[str]:
        columns = [c if isinstance(c, str) else c[0] for c in columns if c[0] != PREFIX_FIELD]  ###
        html_code_lines = self.get_html_table_code(records, columns, count, with_title, style=style)
        return map(lambda i: i.replace(SPACE * 2, HTML_SPACE * 2, html_code_lines))

    @staticmethod
    def get_html_text_code(text: Iterable, level: Optional[int] = None, style=AUTO) -> str:
        if isinstance(text, str):
            text = text.split('\n')
        assert isinstance(text, Iterable), f'got {text}'
        text = '<br>\n'.join(text)
        if level:
            tag = f'h{level}'
            style = Auto.acquire(style, H_STYLE)
        else:
            tag = 'p'
            style = Auto.acquire(style, P_STYLE)
        open_tag = f'<{tag} style="{style}">' if style else f'<{tag}>'
        close_tag = f'</{tag}>'
        return f'{open_tag}{text}{close_tag}'

    @staticmethod
    def get_html_table_code(
            records: Iterable,
            columns: Sequence,
            count: AutoCount = None,
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


if HTML:
    DisplayMixin.display = HtmlFormat
