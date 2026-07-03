"""Scope-aware import-usage analysis (#5).

Two properties matter here:

1. **False-negative fixes** — imports shadowed by a parameter, or used only in an
   unrelated scope, are now recognized as unused.
2. **No false positives** — the analysis only ever downgrades a flat-"used"
   import to unused, and must NEVER do so for an import that is genuinely used.
   The FP-guard cases below are the ones most likely to break a naive scope
   model (values evaluated in the enclosing scope, closures, comprehensions,
   protected names). A regression here would make ``--cleanup`` delete live code.
"""

import ast
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest  # noqa: E402

from checker import ImportChecker  # noqa: E402


def _unused_names(code):
    checker = ImportChecker()
    tree = ast.parse(code)
    imports = checker.extract_imports_from_ast(tree)
    references = checker.extract_name_references(tree)
    used, unused = checker.analyze_imports(imports, references)
    used, unused = checker._refine_with_scopes(tree, used, unused)
    return sorted(checker._bound_name(i) for i in unused)


class TestScopeFalseNegativeFixes:
    def test_param_shadows_module_import(self):
        assert _unused_names("from os import path\ndef f(path):\n    return path\n") == ["path"]

    def test_function_local_import_used_in_other_function(self):
        code = "def f():\n    import os\ndef g():\n    return os.getcwd()\n"
        assert _unused_names(code) == ["os"]

    def test_comprehension_target_shadows_unused_import(self):
        assert _unused_names("import os\nresult = [os for os in range(3)]\n") == ["os"]


# Each of these uses the import for real; the analysis must NOT flag it.
_NO_FALSE_POSITIVE = {
    "module_use": "import os\nprint(os.getcwd())\n",
    "closure": "import os\ndef f():\n    return os.getcwd()\n",
    "nested_closure": "import os\ndef a():\n    def b():\n        return os.sep\n    return b\n",
    "default_arg_value": "import os\ndef f(x=os.getcwd()):\n    return x\n",
    "kwonly_default": "import os\ndef f(*, x=os.sep):\n    return x\n",
    "lambda_default": "import os\nf = lambda x=os.sep: x\n",
    "arg_annotation": "import os\ndef f(x: os.PathLike):\n    return x\n",
    "return_annotation": "import os\ndef f() -> os.PathLike:\n    return 1\n",
    "decorator": "import functools\n@functools.wraps\ndef f():\n    pass\n",
    "class_base": "import collections\nclass C(collections.OrderedDict):\n    pass\n",
    "class_body": "import os\nclass C:\n    x = os.sep\n",
    "method_uses_module_import": "import os\nclass C:\n    def m(self):\n        return os.getcwd()\n",
    "nested_class_method": "import os\nclass A:\n    class B:\n        def m(self):\n            return os.sep\n",
    "comp_outer_iterable": "import os\ndata = [x for x in os.listdir()]\n",
    "comp_element": "import os\ndata = [os.stat(x) for x in range(3)]\n",
    "dict_comp_value": "import os\nd = {k: os.stat(k) for k in range(3)}\n",
    "augmented_assign": "import os\nos = os.getcwd()\nprint(os)\n",
    "assigned_then_used": "import os\np = os\nprint(p.getcwd())\n",
    "global_decl": "import os\ndef f():\n    global os\n    os = 1\nprint(os)\n",
    "nonlocal_decl": (
        "def outer():\n    import os\n    def inner():\n        nonlocal os\n"
        "        os = 1\n    inner()\n    return os\n"
    ),
    "walrus": "import os\nif (p := os.getcwd()):\n    print(p)\n",
    "fstring": 'import os\nprint(f"{os.sep}")\n',
    "module_use_plus_shadow": "from os import path\nx = path\ndef f(path):\n    return path\n",
    "try_except_fallback": (
        "try:\n    import json\nexcept ImportError:\n    import simplejson as json\n" "print(json.dumps({}))\n"
    ),
    "conditional_import": "import sys\nif True:\n    import os\nprint(os.getcwd(), sys.argv)\n",
    "all_export": 'from x import Thing\n__all__ = ["Thing"]\n',
    "type_checking_forward_ref": (
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from decimal import Decimal\n"
        'def f(x: "Decimal"):\n    return x\n'
    ),
    "star_import": "from os.path import *\nprint(join('a', 'b'))\n",
}


@pytest.mark.parametrize("code", list(_NO_FALSE_POSITIVE.values()), ids=list(_NO_FALSE_POSITIVE))
def test_no_false_positive(code):
    assert _unused_names(code) == []
