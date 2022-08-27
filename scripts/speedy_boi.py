from __future__ import print_function

from timeit import timeit


def checkit(base_val):
    vars = 'abc="{base_val}";'.format(base_val=base_val)
    actions = [
        'ghi = f"{abc}def"',
        'ghi = abc + "def"',
        'ghi = "{abc}def".format(abc=abc)',
        'abc += "def"',
    ]
    results = []   

    for a in actions:
        cmd = f'{vars} {a}'
        try:
            results.append(timeit(cmd, number=1_000_000))
        except:
            results.append('Action %s failed.' % a)
    print("f-string: {0}\nplus: {1}\nplus_equals: {3}\nformat: {2}\n".format(*results))

base_val = "abc"
print("::Small input benchmark::")
checkit(base_val)
print("::Large input benchmark::")
checkit(base_val*10_000)
