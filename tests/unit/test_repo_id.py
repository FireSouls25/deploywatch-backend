import pytest

from app.domain.repo import GithubRepoId


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("octo/Hello-World", "octo/hello-world"),  # forma corta
        ("https://github.com/Octo/Repo", "octo/repo"),  # URL https
        ("https://github.com/Octo/Repo.git", "octo/repo"),  # sufijo .git
        ("https://github.com/octo/repo/", "octo/repo"),  # barra final
        ("  octo/repo  ", "octo/repo"),  # espacios alrededor
        ("git@github.com:octo/repo.git", "octo/repo"),  # SSH
    ],
)
def test_parse_valid_references(raw, expected):
    assert GithubRepoId.parse(raw).full_name == expected


@pytest.mark.parametrize(
    "raw",
    [
        "not-a-repo",  # sin owner
        "",  # vacío
        "octo/repo/extra",  # demasiados segmentos
        "https://github.com/octo",  # URL sin repo
        "https://github.com/octo/re po",  # espacio dentro del nombre
    ],
)
def test_parse_invalid_references(raw):
    with pytest.raises(ValueError):
        GithubRepoId.parse(raw)
