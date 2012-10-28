#!/usr/bin/python

import sys
import os
import shutil
import re
import pwd

from subprocess import call
from tempfile import mkdtemp

from urllib2 import urlopen
from zipfile import ZipFile

def run():
    os.chdir(os.path.dirname(__file__))

    call([
        "svn", "checkout",
        "http://closure-library.googlecode.com/svn/trunk/",
        "closure-library"])

    tmp_dir = mkdtemp()

    with open(os.path.join(tmp_dir, "compiler-latest.zip"), "w") as f:
        f.write(urlopen("http://closure-compiler.googlecode.com/files/compiler-latest.zip").read())

    with open("closure-compiler.jar", "w") as f:
        f.write(ZipFile(open(os.path.join(tmp_dir, "compiler-latest.zip")), "r").open("compiler.jar").read())

    with open(os.path.join(tmp_dir, "closure-templates-for-javascript-latest.zip"), "w") as f:
        f.write(urlopen("http://closure-templates.googlecode.com/files/closure-templates-for-javascript-latest.zip").read())

    with open(os.path.join("soy", "SoyToJsSrcCompiler.jar"), "w") as f:
        f.write(ZipFile(open(os.path.join(tmp_dir, "closure-templates-for-javascript-latest.zip")), "r").open("SoyToJsSrcCompiler.jar").read())

    with open(os.path.join("soy", "soyutils_usegoog.js"), "w") as f:
        f.write(ZipFile(open(os.path.join(tmp_dir, "closure-templates-for-javascript-latest.zip")), "r").open("soyutils_usegoog.js").read())

    with open(os.path.join(tmp_dir, "closure-templates-msg-extractor-latest.zip"), "w") as f:
        f.write(urlopen("http://closure-templates.googlecode.com/files/closure-templates-msg-extractor-latest.zip").read())

    with open(os.path.join("soy", "SoyMsgExtractor.jar"), "w") as f:
        f.write(ZipFile(open(os.path.join(tmp_dir, "closure-templates-msg-extractor-latest.zip")), "r").open("SoyMsgExtractor.jar").read())

    # FIXME this is not a "latest" release...
    with open("closure-stylesheets.jar", "w") as f:
        f.write(urlopen("https://closure-stylesheets.googlecode.com/files/closure-stylesheets-20111230.jar").read())


if __name__ == "__main__":
    run()
