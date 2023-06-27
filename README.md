# lockeye

Used to track changes of text sample from another file

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
![Linux](https://img.shields.io/sourceforge/platform/platform?color=green&logo=Linux)

# usage

there is minimum 2 files involved

1. reference file. for instance `doc.rst`
2. source file with the code. for instance `do.py`

doc.rst

```
This is a Doc file
...
this will print FooBar in a complex way. see example

.. code-block:: python

  # lockeye: source/do.py +3
  def complex(bar=1):
    if bar == 1:
      print("foo")
    elif bar == 2:
      print("foo-bar")
    else
      print("bar-bar")
.. lockeye-stop

.. code-block:: python
  # lockeye: source/do.py +11
  def simple():
    print("bar")
  # lockeye-stop

  some other code

```

do.py

```
import os

def complex(bar=1):
  if bar == 1:
    print("foo")
  elif bar == 2:
    print("foo-bar")
  else
    print("bar-bar")

def simple():
  print("bar")

if __name__ == "__main__":
  pass

```

The lockeye will check every commit that code inside of `lockeye:` and `lockeye-stop`
exactly match the code in source file.

* The line counting start from 1 and derective `# lockeye: source/do.py +11` start comparing
  will skip 10 first line of the source file.
* The lines with only spaces are not compared and assumed as equal
* Since rst format code block has identation lockeye will remove spaces from each line of the
  code as match as exists untill first character
  in line containing derective `  # lockeye: source/do.py +11` -> 2 chars


## configure pre-commit

add configuration to `.pre-commit-config.yaml` file of your repo

```
  - repo: https://github.com/worroc/lockeye
    rev: v0.0.4
    hooks:
      - id: lockeye
        args: ['--log-level', 'error', '--pattern', '*.rst', '*.md', '--anchor', 'lockeye']
```

or add -- as last parameter to prevent modified files from been added
as values to previous parameter

```
        args: ['--log-level', 'error', '--pattern', '*.rst', '*.md', '--']
```

# developing

The simplest way to developing is working on the sources

1. clone the repo `git clone git@github.com:worroc/lockeye.git`
    for example to ~/projects/
2. configure the debug level in `.pre-commit-config.yaml` of your repo.
3. make some change (it should cause lockeye to fail) and run git commit.
The `lockeye` hook will print location of the hook source file
4. replace this file with a link to a cloned plugin
    ln -sf ~/projects/lockeye/lockeye/main.py <file location from last run>

Now any changes in repo will in action.
