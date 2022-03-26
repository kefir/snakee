DEFAULT_ENCODING = 'utf8'

JUPYTER_LINE_LEN = 120
LONG_LINE_LEN = 900
DEFAULT_LINE_LEN = JUPYTER_LINE_LEN

EMPTY = ''
SPACE = ' '
DOT = '.'
COMMA = ','
STAR = '*'
PIPE = '|'
DASH = '-'
UNDER = '_'
EQUAL = '='

ALL = STAR
DEFAULT_STR = DASH
FILL_CHAR = SPACE
REPR_DELIMITER = SPACE
NOT_SET = UNDER
SHORT_CROP_SUFFIX = UNDER
CROP_SUFFIX = DOT * 2
ELLIPSIS = DOT * 3
EQUALITY = EQUAL * 2
TITLE_PREFIX = EQUAL * 3
SMALL_INDENT = SPACE * 2
PY_INDENT = SPACE * 4
DEFAULT_ITEMS_DELIMITER = COMMA + SPACE

TAB_CHAR, TAB_SUBSTITUTE = '\t', ' -> '
RETURN_CHAR, RETURN_SUBSTITUTE = '\r', ' <- '
PARAGRAPH_CHAR, PARAGRAPH_SUBSTITUTE = '\n', ' \\n '

DEFAULT_TRUE_STR = 'Yes'
DEFAULT_FALSE_STR = 'No'
FALSE_VALUES = 'false', 'no', '-', '0', '0.0', ''
