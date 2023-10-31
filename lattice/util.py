import re

def snake_style(s):
    #return ''.join(['_'+c.lower() if c.isupper() else c for c in s]).lstrip('_')
    a = re.compile('((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))')
    return a.sub(r'_\1', s).lower()
