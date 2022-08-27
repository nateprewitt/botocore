from timeit import timeit


def checkit(base_val):
    vars = f'abc="{base_val}";'
    actions = [
        'ghi = f"{abc}def"',
        'ghi = abc + "def"',
        'ghi = "{abc}def".format(abc=abc)',
        'abc += "def"',
    ]
    results = []   

    for a in actions:
        cmd = f'{vars} {a}'
        results.append(timeit(cmd, number=1_000_000))
    print(f"""
    f-string: {results[0]}
    plus: {results[1]}
    plus_equals: {results[3]}
    format: {results[2]}
    """)

base_val = "abc"
print("::Small input benchmark::")
checkit(base_val)
print("::Large input benchmark::")
checkit(base_val*10_000)
