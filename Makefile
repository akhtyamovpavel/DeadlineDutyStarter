# Три команды, которые должны работать в любом проекте курса.
# Их наличие проверяется на занятии: агенту нужен воспроизводимый способ
# запустить проект и убедиться, что он не сломан.

.PHONY: install run test push hooks

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

run:
	.venv/bin/uvicorn app.main:app --reload

test:
	.venv/bin/pytest -q

push:
	bash scripts/push_and_check.sh

hooks:
	bash scripts/install_hooks.sh
