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
    description=".",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=f"https://github.com/m3trik/{__package__}",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
        "Operating System :: OS Independent",
    ],
    packages=setuptools.find_packages(),
    # Self-describe as a uitk external tool — ExternalToolHandler's
    # discover() registers this automatically with no host edits. The
    # ``.in_process`` group declares the preferred launch mode (run
    # under the host's existing Qt loop instead of spawning a new
    # interpreter). Bracketed ``[extras]`` would become tags in the
    # browser — none are declared here; add them only when there's a
    # real classification need.
    entry_points={
        "uitk.external_tools.in_process": [
            "map_compositor = map_compositor:MapCompositorUI",
        ],
    },
    include_package_data=True,
    install_requires=ptk.PackageManager.update_requirements(exc=["Pillow", "qtpy"]),
    data_files=ptk.get_dir_contents(
        __package__,
        "filepath",
        exc_files=["*.py", "*.pyc", "*.json", "*.bak"],
        recursive=True,
    ),
)

# --------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
