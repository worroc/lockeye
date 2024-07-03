#!/usr/bin/env python

from setuptools import find_packages, setup

LICENSE = "LICENSE"
README = "README.md"
with open(README) as f:
    readme = f.read()

with open(LICENSE) as f:
    license = f.read()


setup(
    name="lockeye",
    version="0.0.3",
    description="code monitor",
    long_description=readme,
    author="Worroc",
    author_email="worroc@zoho.com",
    url="https://github.com/worroc/lockeye",
    license=license,
    packages=find_packages(),
    install_requires=(),
    classifiers=[
        "Development Status :: 1 - Beta" "Intended Audience :: Developers",
        "Natural Language :: English",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
    entry_points={"console_scripts": ("lockeye=lockeye.main:main", "exclude-marked=exclude_marked.main:main")},
    data_files=[("", [LICENSE, README])],
)
