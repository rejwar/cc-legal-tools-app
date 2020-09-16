import posixpath
import re
import urllib

from bs4 import NavigableString
from polib import POEntry, POFile

from i18n import LANGUAGE_CODE_REGEX

from .constants import EXCLUDED_LICENSE_VERSIONS
from .models import LegalCode, License


def get_code_from_jurisdiction_url(url):
    pieces = urllib.parse.urlsplit(url).path.strip("/").split("/")
    try:
        code = pieces[1]
    except IndexError:
        code = ""
    return code


def get_license_url_from_legalcode_url(legalcode_url):
    """
    Return the URL of the license that this legalcode url is for.
    Legalcode URLs are like
    http://creativecommons.org/licenses/by/4.0/legalcode
    http://creativecommons.org/licenses/by/4.0/legalcode.es
    http://opensource.org/licenses/bsd-license.php

    License URLs are like
    http://creativecommons.org/licenses/by-nc-nd/4.0/
    http://creativecommons.org/licenses/BSD/
    """
    if legalcode_url == "http://opensource.org/licenses/bsd-license.php":
        return "http://creativecommons.org/licenses/BSD/"
    if legalcode_url == "http://opensource.org/licenses/mit-license.php":
        return "http://creativecommons.org/licenses/MIT/"

    regex = re.compile(r"^(.*)legalcode(\.%s)?" % LANGUAGE_CODE_REGEX)
    m = regex.match(legalcode_url)
    if m:
        return m.group(1)
    raise ValueError(f"regex did not match {legalcode_url}")


def parse_legalcode_filename(filename):
    """
    Given the filename where the HTML text of a license is stored,
    return a dictionary with the metadata we can figure out from it.

    The filename should not include any path. A trailing .html is okay.

    COPIED FROM
    https://github.com/creativecommons/cc-link-checker/blob/6bb2eae4151c5f7949b73f8d066c309f2413c4a5/link_checker.py#L231
    and modified a great deal.
    """

    basename = filename
    if basename.endswith(".html"):
        basename = basename[:-5]

    parts = basename.split("_")

    license = parts.pop(0)
    if license == "samplingplus":
        license = "sampling+"
    elif license == "nc-samplingplus":
        license = "nc-sampling+"

    license_code_for_url = license

    version = parts.pop(0)

    jurisdiction = None
    language = None
    if license.startswith("zero"):
        license_code_to_return = "CC0"
        path_base = "publicdomain"
    else:
        license_code_to_return = license
        path_base = "licenses"
        if parts and float(version) < 4.0:
            jurisdiction = parts.pop(0)

    if parts:
        language = parts.pop(0)

    if language:
        legalcode = f"legalcode.{language}"
    else:
        legalcode = False

    url = posixpath.join("http://creativecommons.org", path_base)
    url = posixpath.join(url, license_code_for_url)
    url = posixpath.join(url, version)

    if jurisdiction:
        url = posixpath.join(url, jurisdiction)

    if legalcode:
        url = posixpath.join(url, legalcode)
    else:
        url = f"{url}/"

    data = dict(
        license_code=license_code_to_return,
        version=version,
        jurisdiction_code=jurisdiction or "",
        language_code=language or "",
        url=url,
        about_url=compute_about_url(license_code_for_url, version, jurisdiction or ""),
    )

    return data


# Django Distill Utility Functions


def get_licenses_code_and_version():
    """Returns an iterable of license dictionaries
    dictionary keys:
        - license_code
        - version
    """
    for license in License.objects.exclude(version__in=EXCLUDED_LICENSE_VERSIONS):
        yield {
            "license_code": license.license_code,
            "version": license.version,
        }


def get_licenses_code_version_language_code():
    """Returns an iterable of license dictionaries
    dictionary keys:
        - license_code
        - version
        - language_code (
            value is a translated license's
            language_code
        )
    """
    for legalcode in LegalCode.objects.exclude(
        license__version__in=EXCLUDED_LICENSE_VERSIONS
    ):
        license = legalcode.license
        item = {
            "license_code": license.license_code,
            "version": license.version,
            "language_code": legalcode.language_code,
        }
        yield item


def compute_about_url(license_code, version, jurisdiction_code):
    """
    Compute the canonical unique "about" URL for a license with the given attributes.
    Note that a "license" is language-independent, unlike a LegalCode
    but it can have a jurisdiction.q

    E.g.

    http://creativecommons.org/licenses/BSD/
    http://creativecommons.org/licenses/GPL/2.0/
    http://creativecommons.org/licenses/LGPL/2.1/
    http://creativecommons.org/licenses/MIT/
    http://creativecommons.org/licenses/by/2.0/
    http://creativecommons.org/licenses/publicdomain/
    http://creativecommons.org/publicdomain/zero/1.0/
    http://creativecommons.org/publicdomain/mark/1.0/
    http://creativecommons.org/licenses/nc-sampling+/1.0/
    http://creativecommons.org/licenses/devnations/2.0/
    http://creativecommons.org/licenses/by/3.0/nl/
    http://creativecommons.org/licenses/by-nc-nd/3.0/br/
    http://creativecommons.org/licenses/by/4.0/
    http://creativecommons.org/licenses/by-nc-nd/4.0/
    """
    base = "http://creativecommons.org"
    if license_code in ["BSD", "MIT"]:
        return f"{base}/licenses/{license_code}/"
    if "GPL" in license_code:
        return f"{base}/licenses/{license_code}/{version}/"
    prefix = "publicdomain" if license_code in ["CC0", "zero", "mark"] else "licenses"
    mostly = f"{base}/{prefix}/{license_code}/{version}/"
    if jurisdiction_code:
        return f"{mostly}{jurisdiction_code}/"
    return mostly


def validate_list_is_all_text(l):
    """
    Just for sanity, make sure all the elements of a list are types that
    we expect to be in there.  Convert it all to str and return the
    result.
    """
    newlist = []
    for i, value in enumerate(l):
        if type(value) == NavigableString:
            newlist.append(str(value))
            continue
        elif type(value) not in (str, list, dict):
            raise ValueError(f"Not a str, list, or dict: {type(value)}: {value}")
        if isinstance(value, list):
            newlist.append(validate_list_is_all_text(value))
        elif isinstance(value, dict):
            newlist.append(validate_dictionary_is_all_text(value))
        else:
            newlist.append(value)
    return newlist


def validate_dictionary_is_all_text(d):
    """
    Just for sanity, make sure all the keys and values of a dictionary are types that
    we expect to be in there.
    """
    newdict = dict()
    for k, v in d.items():
        assert isinstance(k, str)
        if type(v) == NavigableString:
            newdict[k] = str(v)
            continue
        elif type(v) not in (str, dict, list):
            raise ValueError(f"Not a str: k={k} {type(v)}: {v}")
        if isinstance(v, dict):
            newdict[k] = validate_dictionary_is_all_text(v)
        elif isinstance(v, list):
            newdict[k] = validate_list_is_all_text(v)
        else:
            newdict[k] = v
    return newdict


def save_dict_to_pofile(pofile: POFile, messages: dict):
    """
    We have a dictionary mapping string message keys to string message values
    or dictionaries of the same.
    Write out a .po file of the data.
    """
    for message_key, value in messages.items():
        pofile.append(POEntry(msgid=message_key, msgstr=value.strip()))
