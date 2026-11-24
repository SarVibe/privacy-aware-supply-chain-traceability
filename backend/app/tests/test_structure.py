"""Enforce research-package boundaries using parsed Python source."""

import ast
from importlib.util import resolve_name

from src.common.paths import app_dir

APPLICATION = app_dir()
SCOPE = {"rq1", "rq2", "rq3"}
SERVING_FILES = {"harmonization_pipeline.py", "blockchain_client.py", "bitarray_differential_privacy.py"}
HISTORICAL_APPLICATION_CONFIG = {
    ("experiments", "rq1", "grid_runner.py"),
}
RETIRED_SHARED_NAMES = {
    "BloomEncoder", "qgrams", "qgram_set", "add_noise", "add_typos", "inject_typo", "_inject_noise",
}


def research_sources():
    for question in sorted(SCOPE):
        for path in (APPLICATION / "experiments" / question).rglob("*.py"):
            yield question, path
        if question != "rq1":
            for path in (APPLICATION / "src" / question).rglob("*.py"):
                if path.name not in SERVING_FILES:
                    yield question, path


def parsed(path):
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def local_imports(path, tree):
    parent = ".".join(path.relative_to(APPLICATION).parts[:-1])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = resolve_name("." * node.level + module, parent)
            for alias in node.names:
                yield f"{module}.{alias.name}"


def test_research_modules_do_not_import_other_research_questions():
    violations = []
    for question, path in research_sources():
        relative = path.relative_to(APPLICATION)
        for module in local_imports(path, parsed(path)):
            root, namespace, *_ = (*module.split("."), "")
            if root not in {"experiments", "src"}:
                continue
            if namespace == question or (root, namespace) == ("src", "common"):
                continue
            if namespace == "application_config" and relative.parts in HISTORICAL_APPLICATION_CONFIG:
                continue
            violations.append(f"{relative}: {module}")
    assert not violations, "\n".join(violations)


def shared_definitions(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in RETIRED_SHARED_NAMES or (not node.name.startswith("_") and node.name != "main"):
                yield node.name, node.lineno


def test_research_modules_do_not_redefine_shared_implementations():
    common = APPLICATION / "src" / "common"
    common_names = {name for path in common.rglob("*.py") for name, _ in shared_definitions(parsed(path))}
    violations = []
    for _, path in research_sources():
        tree = parsed(path)
        for name, line in shared_definitions(tree):
            if name in common_names | RETIRED_SHARED_NAMES:
                violations.append(f"{path.relative_to(APPLICATION)}:{line}: {name}")
    assert not violations, "\n".join(violations)


def test_serving_uses_no_local_preprocessing_or_legacy_encoder_imports():
    active = [
        APPLICATION / "main.py",
        APPLICATION / "src/rq1/entity_resolver.py",
        *(APPLICATION / "src/rq2" / name for name in SERVING_FILES),
    ]
    historical = {"KeyedBloomFilter", "QGramExtractor", "TextPreprocessor"}
    shared = {"BloomFilterEncoder", "CompositeBloomEncoder", "encode_record", "extract_qgrams", "normalize"}
    for path in active:
        tree = parsed(path)
        assert not ({module.split(".")[-1] for module in local_imports(path, tree)} & historical), path
        assert not ({name for name, _ in shared_definitions(tree)} & (shared | historical)), path
