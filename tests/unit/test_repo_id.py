import pytest

from app.domain.repo import GithubRepoId


def test_parse_short_form():
    assert GithubRepoId.parse("octo/Hello-World").full_name == "octo/hello-world"


def test_parse_url_with_git_suffix():
    gid = GithubRepoId.parse("https://github.com/Octo/Repo.git")
    assert (gid.owner, gid.repo) == ("octo", "repo")


def test_parse_invalid():
    with pytest.raises(ValueError):
        GithubRepoId.parse("not-a-repo")
