"""The one rule about models that nothing else enforces.

`CustomBase` in `yt_shared/db/session.py` declares its primary key as
``id: uuid.UUID = sa.Column(...)`` — a legacy annotation, not ``Mapped[...]``.
Recent SQLAlchemy refuses to copy such an attribute into a subclass and raises
`MappedAnnotationError` at import time, which takes down every service at once
because all three import `yt_shared.models`.

Nobody found out for years because every model that shipped declares its own
`id` and so never inherits the annotated one. The first two that did not
(`PendingDownload`, `StartupMessage`) broke the whole stack on the next rebuild,
when the resolved SQLAlchemy happened to be new enough to care.

Fixing the base is the better repair and is not this test's job; until someone
does it, this keeps the next model from finding the same hole. It reads the
source rather than importing anything: importing `yt_shared.models` builds the
database engine, which would put asyncpg and a full environment on the path of
a check that needs neither.
"""

import ast
import pathlib

import pytest

MODELS_DIR = pathlib.Path(__file__).parents[1] / 'src' / 'yt_shared' / 'models'


def model_modules() -> list[pathlib.Path]:
    return sorted(p for p in MODELS_DIR.glob('*.py') if p.name != '__init__.py')


def model_classes(path: pathlib.Path) -> list[ast.ClassDef]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            isinstance(base, ast.Name) and base.id == 'Base' for base in node.bases
        )
    ]


def assigns_id(cls: ast.ClassDef) -> bool:
    return any(
        isinstance(stmt, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == 'id'
            for target in stmt.targets
        )
        for stmt in cls.body
    )


def test_the_models_directory_was_found() -> None:
    """A path that stops matching would make every assertion below vacuous."""
    assert MODELS_DIR.is_dir()
    assert model_modules()


@pytest.mark.parametrize(
    'path', model_modules(), ids=lambda p: p.stem
)
def test_every_model_declares_its_own_primary_key(path: pathlib.Path) -> None:
    classes = model_classes(path)
    assert classes, f'{path.name} defines no model'
    for cls in classes:
        assert assigns_id(cls), (
            f'{cls.name} in {path.name} inherits `id` from CustomBase, whose '
            f'annotation recent SQLAlchemy rejects. Declare it on the model, '
            f'as every other model does.'
        )
