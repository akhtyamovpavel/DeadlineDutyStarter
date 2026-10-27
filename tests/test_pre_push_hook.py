import os
from pathlib import Path
import subprocess


PROJECT = Path(__file__).resolve().parents[1]
HOOK = PROJECT / ".githooks" / "pre-push"

GIT_MOCK = r'''() {
    if [[ "$1" == "symbolic-ref" && "${NO_DEFAULT:-}" != "1" ]]; then
        echo "refs/remotes/origin/main"
        return 0
    fi
    return 1
}'''

GH_MOCK = r'''() {
    if [[ "${API_FAIL:-}" == "1" ]]; then
        return 1
    fi
    if [[ "${PR_MISSING:-}" != "1" ]]; then
        echo "https://github.com/example/project/pull/7"
    fi
}'''


def run_hook(refs, **settings):
    environment = os.environ.copy()
    environment["BASH_FUNC_git%%"] = GIT_MOCK
    environment["BASH_FUNC_gh%%"] = GH_MOCK
    environment.update(settings)
    return subprocess.run(
        ["bash", str(HOOK), "origin", "git@github.com:example/project.git"],
        cwd=PROJECT,
        env=environment,
        input=refs,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_blocks_direct_push_to_default_branch():
    refs = "refs/heads/main abc refs/heads/main def\n"
    result = run_hook(refs)
    assert result.returncode == 1
    assert "Direct pushes to main are blocked" in result.stdout


def test_first_push_requests_pull_request():
    refs = "refs/heads/feature abc refs/heads/feature 000000\n"
    result = run_hook(refs, PR_MISSING="1")
    assert result.returncode == 0
    assert "create a pull request after the push" in result.stdout


def test_existing_branch_requires_open_pull_request():
    refs = "refs/heads/feature abc refs/heads/feature def\n"
    missing = run_hook(refs, PR_MISSING="1")
    assert missing.returncode == 1
    assert "No open pull request" in missing.stdout
    present = run_hook(refs)
    assert present.returncode == 0


def test_unavailable_pr_check_or_default_branch_blocks_push():
    refs = "refs/heads/feature abc refs/heads/feature def\n"
    assert run_hook(refs, API_FAIL="1").returncode == 1
    assert run_hook(refs, NO_DEFAULT="1").returncode == 1


def test_multi_ref_push_cannot_hide_push_to_default_branch():
    refs = "refs/heads/feature abc refs/heads/feature 000000\n"
    refs += "refs/heads/main abc refs/heads/main def\n"
    assert run_hook(refs).returncode == 1
