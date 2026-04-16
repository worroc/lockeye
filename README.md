# lockeye

Used to track changes of text sample from another file

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
![Linux](https://img.shields.io/sourceforge/platform/platform?color=green&logo=Linux)

## usage

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

   # some other code

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
* Since rst format code block has identation lockeye will remove spaces
  from each line of the code as match as exists untill first character
  in line containing derective `  # lockeye: source/do.py +11` -> 2 chars

## configure pre-commit

add configuration to `.pre-commit-config.yaml` file of your repo

```
- repo: https://github.com/worroc/lockeye
  rev: v0.0.2
  hooks:
    - id: lockeye
      args: ['--log-level', 'error', '--pattern',
             '*.rst', '*.md', '*.py', '--anchor', 'lockeye']
```

or add -- as last parameter to prevent modified files from been added
as values to previous parameter

```
args: ['--log-level', 'error', '--pattern', '*.rst', '*.md', '--']
```

## developing

The simplest way to developing is working on the sources

1. clone the repo `git clone git@github.com:worroc/lockeye.git`
    for example to ~/projects/
2. configure the debug level in `.pre-commit-config.yaml` of your repo.
3. make some change (it should cause lockeye to fail) and run git commit.
   The `lockeye` hook will print location of the hook source file
4. replace this file with a link to a cloned plugin
    ln -sf ~/projects/lockeye/lockeye/main.py <file location from last run>

Now any changes in repo will in action.

# exclude-marked

do not allow commit changes marked "NO-COMMIT"

```
 if expression:
   print(f"debug {expression}")  # NO-COMMIT: print expression locally only
   ...
```

## configure pre-commit

add configuration to `.pre-commit-config.yaml` file of your repo

```
- repo: https://github.com/worroc/lockeye
  rev: v0.0.2
  hooks:
    - id: exclude-marked
      args: ['--log-level', 'info', '--marker', 'NO-COMMIT']
```

arguments default values:

* --log-level: info
* --marker: NO-COMMIT

## configure local

```
git pull git@github.com:worroc/lockeye.git
cd lockeye
python -m venv .venv
source .venv/bin/activate
pip install -e .
pwd
```

add configuration to `.pre-commit-config.yaml` file of your repo

```
- repo: local
  hooks:
  - id: exclude-marked
    name: Exclude from commit
    language: system
    entry: <lockeye_repo_directory>/exclude-marked
    description: "Exclude changes to be commited if contains some marker"
    args: ["--marker=NO-COMMIT", "--log-level", "DEBUG"]
    require_serial: true
```

## developing

```
# install & configure
git pull git@github.com:worroc/lockeye.git
cd lockyey
python -m venv .venv
source .venv/bin/activate
pip install -e .

# see in action
echo "NO-COMMIT" >> README.txt
git add README.txt
pre-commit run
```

# sync-hash

Validate that generated files are in sync with their source files.

When a file is auto-generated from a source (e.g. `locations-flex.conf`
generated from `endpoint_capability_matrix.yaml`), embed a hash directive
in the generated file. The `sync-hash` hook computes the actual hash of
the source and fails the commit if it doesn't match — ensuring the
generated file is always up to date.

## How it works

The generated file contains a comment with a sync-hash directive:

```
# lockeye: sync-hash md5 3a8f...b2c1 ../path/to/source.yaml
```

Format: `lockeye: sync-hash <method> <expected_hash> <relative_path>`

- **method** — hash algorithm (`md5`, `sha256`, etc.)
- **expected_hash** — hex digest of the source file at generation time
- **relative_path** — path to the source file, resolved relative to the
  file containing the directive

On commit, the hook scans staged files for this pattern, recomputes the
hash of the referenced source, and fails if they don't match.

## Usage

### 1. In your generator script

Compute the hash of the source file and write the directive into the
generated output:

```python
import hashlib
from pathlib import Path

source = Path("source.yaml")
h = hashlib.md5(source.read_bytes()).hexdigest()
# write into the generated file:
# lockeye: sync-hash md5 {h} ../relative/path/to/source.yaml
```

### 2. Configure pre-commit

Add to `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/worroc/lockeye
  rev: v0.1.0
  hooks:
    - id: sync-hash
```

### 3. Developer workflow

1. Edit the source file
2. Run the generator to regenerate the output
3. Stage both files and commit — the hook validates sync

If you forget to regenerate, the commit is rejected with a clear message
showing expected vs actual hash.

## Running tests

```
uvx pytest tests/ -v
```

# autoink

Auto-increment a version counter in files when they are changed.

Place a `lockeye: autoink <version> <timestamp>` directive in a comment,
followed by a variable assignment that holds the same version:

```powershell
# lockeye: autoink 1 2026-04-16T00:00:00Z
$ScriptVersion = 1
```

```python
# lockeye: autoink 1 2026-04-16T00:00:00Z
VERSION = 1
```

The comment line is the source of truth. On commit the hook compares the
**full directive line** in the staged file to the one in `HEAD`:

- **Identical** — file changed but version not bumped. The hook increments
  the integer, sets the timestamp to now (UTC), and rewrites the file.
  It then checks the next non-blank line; if that line contains the old
  version number it gets the new one mirrored in.
- **Different** — developer already bumped it, hook passes.

The commit is aborted after an auto-increment so you can stage the updated
file and recommit.

## configure pre-commit

```yaml
- repo: https://github.com/worroc/lockeye
  rev: v0.1.3
  hooks:
    - id: autoink
```
