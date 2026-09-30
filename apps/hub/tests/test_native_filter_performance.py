import random
import re
import time

from runtime.remote.security import _sensitive_lines, safe_text


def test_linear_filter_keeps_the_previous_exact_redaction_semantics():
    old = re.compile(r'''(?im)^.*(?:["']?(?:[\w-]*token|api[_-]?key|password|secret)["']?\s*[:=]|os\.environ|process\.env).*$''')
    samples = ['public\r\napi_key=x\r\nlast', 'public prefix token\n \t=hidden\nnext',
        'password=x token\n=second', 'token=one\nsecret=two\npublic', 'os.environ\nprocess.env',
        'notatoken: value', '"MY_TOKEN" : "secret-value"', 'a\npassword\r\n:\r\nbody', 'plain']
    rng=random.Random(42)
    atoms=['x',' ', '\n','\r','\t','token','api-key','password','SECRET','"',"'",'=',':','os.environ','process.env','中文']
    samples += [''.join(rng.choice(atoms) for _ in range(25)) for _ in range(1000)]
    for value in samples:
        assert _sensitive_lines(value) == old.sub('[redacted]',value)


def test_long_plain_line_is_linear_and_credentials_still_disappear():
    text='x'*300_000
    started=time.perf_counter()
    assert safe_text(text)==text
    assert safe_text(text+' SECRET=hidden')=='[redacted]'
    assert time.perf_counter()-started<2
