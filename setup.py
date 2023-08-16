import setuptools

from map_compositor import __package__, __version__
import pythontk as ptk


long_description = ptk.get_file_contents("docs/README.md")
description = ptk.get_text_between_delimiters(
    long_description,
    "<!-- short_description_start -->",
    "<!-- short_description_end -->",
    as_string=True,
)

setuptools.setup(
    name=__package__,
    version=__version__,
    author="Ryan Simpson",
    author_email="m3trik@outlook.com",
    license="LGPLv3",
    data_files=[("", ["COPYING.LESSER"])],
    description=".",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=f"https://github.com/m3trik/{__package__}",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
        "Operating System :: OS Independent",
    ],
    include_package_data=True,
    data_files=ptk.get_dir_contents(
        "map_compositor", "filepath", exc_files=["*.py", "*.pyc", "*.json"]
    ),  # ie. ('uitk/ui/0', ['uitk/ui/0/init.ui']),
)

# --------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
