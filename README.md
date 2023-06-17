# lockeye

Used to track changes of text sample from another file

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
![Linux](https://img.shields.io/sourceforge/platform/platform?color=green&logo=Linux)

Only Linux is supported

## configure pre-commit

add configuration to `.pre-commit-config.yaml` file of your repo

```
  - repo: https://github.com/worroc/lockeye
    rev: v0.0.4
    hooks:
      - id: lockeye
        args: ["--log-level=error"]
```

# developing

The simplest way to developing is working on the sources

1. clone the repo `git clone git@github.com:worroc/lockeye.git`
    for example to ~/projects/
2. configure the debug level in `.pre-commit-config.yaml` of your repo.
3. make some change and run git commit. The `lockeye` hook will print location
    of the hook source file
4. replace this file with a link to a cloned plugin
    ln -sf ~/projects/lockeye/lockeye/main.py <file location from last run>

Now any changes in repo will in action.
