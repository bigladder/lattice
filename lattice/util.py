import re


def snake_style(s):
    # return ''.join(['_'+c.lower() if c.isupper() else c for c in s]).lstrip('_')
    a = re.compile("((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))")
    partial_snake = a.sub(r"_\1", s).lower()
    return "_".join(partial_snake.split("-"))


def hyphen_separated_lowercase_style(s):
    return "-".join(snake_style(s).split("_"))


def namespace_style(s):
    return snake_style(s)
