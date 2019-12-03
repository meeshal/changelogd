# -*- coding: utf-8 -*-
"""Main module."""
import datetime
import glob
import hashlib
import logging
import os
import re
import sys
import typing
from collections import defaultdict
from pathlib import Path

import yaml
from yaml.representer import Representer

from .config import Config

SENTINEL = object()

yaml.add_representer(defaultdict, Representer.represent_dict)


class EntryField:
    name: str
    verbose_name: str
    type: str
    required: bool

    def __init__(self, **data):
        self.name = data.get("name")
        self.verbose_name = data.get("verbose-name")
        self.type = data.get("type", "str")
        self.required = data.get("required", True)
        self._value = SENTINEL

    @property
    def value(self) -> typing.Any:
        value = None
        while value is None:
            value = input(f"{self.verbose_name}: ") or None
            if value is None and not self.required:
                break
        return value


def _is_int(input):
    try:
        int(input)
        return True
    except (ValueError, TypeError):
        return False


def create_entry(config: Config):
    config.load()
    entry_fields = [EntryField(**entry) for entry in config.data.get("entry-fields")]
    message_types = config.data.get("message-types")
    for i, message_type in enumerate(message_types):
        print(f"\t[{i + 1}]: {message_type.get('name')}")
    selection = None
    while not _is_int(selection) or not (0 < int(selection) < len(message_types) + 1):
        if selection is not None:
            print(
                f"Pick a positive number lower than {len(message_types) + 1}",
                file=sys.stderr,
            )
        selection = input("Select message type [1]: ") or 1

    entries = {entry.name: entry.value for entry in entry_fields}
    entry_type = message_types[int(selection) - 1].get("name")
    entries["type"] = entry_type

    hash = hashlib.md5()
    entries_flat = " ".join(f"{key}={value}" for key, value in entries.items())
    hash.update(entries_flat.encode())

    output_file = config.path / f"{entry_type}.{hash.hexdigest()[:8]}.entry.yaml"
    with output_file.open("w") as output_fh:
        yaml.dump(entries, output_fh)

    logging.warning(f"Created changelog entry at {output_file.absolute()}")


def prepare_draft(config: Config, version: str):
    config.load()
    releases_dir = config.path / "releases"
    release = create_new_release(config, version)

    releases = prepare_releases(release, releases_dir)

    from pprint import pprint

    pprint(releases)


def prepare_releases(
    release: typing.Dict, releases_dir: Path
) -> typing.List[typing.Dict]:
    versions: typing.Dict[int, Path] = dict()
    for item in os.listdir(releases_dir.as_posix()):
        match = re.match(r"(\d+).*\.ya?ml", item)
        if match:
            version = int(match.group(1))
            if version in versions:
                sys.exit(f"The version {version} is duplicated.")
            versions[version] = releases_dir / match.group(0)
    previous_release = None
    releases = []
    for version in sorted(versions.keys()):
        with versions[version].open() as release_fh:
            release_item = yaml.full_load(release_fh)
            release_item["previous-release"] = previous_release
            previous_release = release_item.get("release-version")
            releases.append(release_item)
    release["previous-release"] = previous_release
    releases.append(release)
    return releases


def create_new_release(config, version):
    entries = glob.glob(str(config.path.absolute() / "*.entry.yaml"))
    release = {
        "entries": defaultdict(list),
        "release-version": version,
        "release-date": datetime.date.today().strftime("%Y-%m-%d"),
        "release-description": input("Release description (hit ENTER to omit): "),
    }
    for entry in entries:
        with open(entry) as entry_file:
            entry_data = yaml.full_load(entry_file)
        release["entries"][entry_data.pop("type")] = entry_data
    return release
