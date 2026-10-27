import os
from pathlib import Path
import subprocess


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts" / "push_and_check.sh"

GIT_MOCK = r'''() {
    case "$1" in
        symbolic-ref)
            if [[ "${*: -1}" == "HEAD" ]]; then
                echo "${BRANCH:-feature}"
            else
                echo "refs/remotes/origin/main"
            fi
            ;;
        rev-parse) echo "new-commit" ;;
        remote) echo "git@github.com:example/project.git" ;;
        ls-remote) echo "${REMOTE_COMMIT:-old-commit} refs/heads/feature" ;;
        push)
            if [[ "${PUSH_FAIL:-}" == "1" ]]; then
                return 1
            fi
            touch "$PUSH_MARKER"
            ;;
        *) return 1 ;;
    esac
}'''

GH_MOCK = r'''() {
    case "$1 $2" in
        "auth status") return 0 ;;
        "run list")
            if [[ -f "$PUSH_MARKER" ]]; then
                echo "102"
            else
                echo "101"
            fi
            ;;
        "run watch")
            echo "Watching run $3"
            if [[ "${CI_FAIL:-}" == "1" ]]; then
                return 1
            fi
            ;;
        "run view") echo "Failed test log" ;;
        "api --method")
            if [[ "${PR_MISSING:-}" != "1" ]]; then
                echo "https://github.com/example/project/pull/7"
            fi
            ;;
        *) return 1 ;;
    esac
}'''


def run_push(tmp_path, **settings):
    environment = os.environ.copy()
    environment["BASH_FUNC_git%%"] = GIT_MOCK
    environment["BASH_FUNC_gh%%"] = GH_MOCK
    environment["PUSH_MARKER"] = str(tmp_path / "pushed")
    environment.update(settings)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=PROJECT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_waits_for_new_run_and_reports_success(tmp_path):
    result = run_push(tmp_path)
    assert result.returncode == 0
    assert "Watching run 102" in result.stdout
    assert "CI passed" in result.stdout
    assert "https://github.com/example/project/pull/7" in result.stdout


def test_failed_run_returns_logs_and_link(tmp_path):
    result = run_push(tmp_path, CI_FAIL="1")
    assert result.returncode == 1
    assert "Failed test log" in result.stdout
    assert "https://github.com/example/project/actions/runs/102" in result.stdout


def test_failed_push_does_not_watch_ci(tmp_path):
    result = run_push(tmp_path, PUSH_FAIL="1")
    assert result.returncode != 0
    assert "Watching run" not in result.stdout


def test_unchanged_branch_checks_existing_ci_and_pull_request(tmp_path):
    result = run_push(tmp_path, REMOTE_COMMIT="new-commit")
    assert result.returncode == 0
    assert "Watching run 101" in result.stdout
    assert "https://github.com/example/project/pull/7" in result.stdout
    assert not (tmp_path / "pushed").exists()


def test_missing_pull_request_fails_after_ci(tmp_path):
    result = run_push(tmp_path, PR_MISSING="1")
    assert result.returncode == 1
    assert "No open pull request" in result.stdout


def test_direct_push_to_default_branch_is_rejected(tmp_path):
    result = run_push(tmp_path, BRANCH="main")
    assert result.returncode == 1
    assert "Direct pushes to main are blocked" in result.stdout
    assert not (tmp_path / "pushed").exists()
