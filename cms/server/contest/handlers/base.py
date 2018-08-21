#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2016 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2015 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
# Copyright © 2015-2016 William Di Luigi <williamdiluigi@gmail.com>
# Copyright © 2016 Myungwoo Chun <mc.tamaki@gmail.com>
# Copyright © 2016 Amir Keivan Mohtashami <akmohtashami97@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Base handler classes for CWS.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import pkg_resources
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import logging
import os
from functools import wraps, partial
from hmac import compare_digest

from flask import Flask, current_app, send_from_directory
from flask import g, abort, session, escape
from flask import request, render_template
from jinja2 import PackageLoader, StrictUndefined
from six import iterkeys
from werkzeug.exceptions import HTTPException, NotFound

from cms import config
from cms.db import Contest, Session
from cms.locale import DEFAULT_TRANSLATION
from cms.server.jinja2_toolbox import \
    instrument_generic_toolbox as global_instrument_generic_toolbox, \
    instrument_cms_toolbox as global_instrument_cms_toolbox, \
    instrument_formatting_toolbox as global_instrument_formatting_toolbox
from cms.server.contest.jinja2_toolbox import \
    instrument_cms_toolbox as cws_instrument_cms_toolbox, \
    instrument_formatting_toolbox as cws_instrument_formatting_toolbox
from cmscommon.datetime import utc as utc_tzinfo, \
    make_datetime, local_tz as local_tzinfo
from cms.server.file_middleware import fetch as base_fetch
from cmscommon.binary import bin_to_b64, b64_to_bin

logger = logging.getLogger(__name__)


class WebServer(Flask):

    def __init__(self, import_name, static_map=None):
        super(WebServer, self).__init__(import_name, static_folder=None)

        self.static_map = static_map or {}
        self.add_url_rule("/<prefix>/<path:filename>", endpoint="static",
                          view_func=self.serve_static_file)

        # Load templates from CWS's package (use package rather than file
        # system as that works even in case of a compressed distribution).
        self.jinja_loader = PackageLoader('cms.server.contest', 'templates')
        # Force autoescape of string, always and forever.
        self.select_jinja_autoescape = True
        # Don't check the disk every time to see whether the templates'
        # files have changed.
        self.templates_auto_reload = False
        self.jinja_options = dict(
            # These cause a line that only contains a control block to be
            # suppressed from the output, making it more readable.
            trim_blocks=True, lstrip_blocks=True,
            # This causes an error when we try to render an undefined value.
            undefined=StrictUndefined,
            # Cache all templates, no matter how many.
            cache_size=-1,
            # Allow the use of {% trans %} tags to localize strings.
            extensions=['jinja2.ext.i18n'])
        # This compresses all leading/trailing whitespace and line breaks of
        # internationalized messages when translating and extracting them.
        self.jinja_env.policies['ext.i18n.trimmed'] = True
        global_instrument_generic_toolbox(self.jinja_env)
        global_instrument_cms_toolbox(self.jinja_env)
        global_instrument_formatting_toolbox(self.jinja_env)
        cws_instrument_cms_toolbox(self.jinja_env)
        cws_instrument_formatting_toolbox(self.jinja_env)

    def serve_static_file(self, prefix, filename):
        directories = self.static_map.get(prefix, [])
        cache_timeout = self.get_send_file_max_age(filename)
        for directory in directories:
            try:
                return send_from_directory(directory, filename,
                                           cache_timeout=cache_timeout)
            except NotFound:
                continue
        else:
            raise NotFound()


app = WebServer('cms.server.contest', {"static": [pkg_resources.resource_filename("cms.server", "static"),
                                                  pkg_resources.resource_filename("cms.server.contest", "static")],
                                       "/stl": config.stl_path})


# TODO What was this for again?
@app.teardown_appcontext
def shutdown_session(exception=None):
    #with ScopedSession() as session:
    #    session.remove()
    pass


XSRF_TOKEN_SIZE = 16


def generate_xsrf_token():
    return os.urandom(XSRF_TOKEN_SIZE)


def salt_xsrf_token(token):
    if not isinstance(token, bytes):
        raise TypeError("token isn't bytes: %s" % type(token))
    if len(token) != XSRF_TOKEN_SIZE:
        raise ValueError("token isn't %d bytes long: %d"
                         % (XSRF_TOKEN_SIZE, len(token)))
    salt = os.urandom(XSRF_TOKEN_SIZE)
    salted_token = bytes(s ^ t for s, t in zip(salt, token))
    return bin_to_b64(salt + salted_token)


def unsalt_xsrf_token(value):
    if not isinstance(value, str):
        raise TypeError("value isn't str: %s" % type(value))
    try:
        value = b64_to_bin(value)
    except ValueError:
        raise ValueError("value isn't base64-encoded bytes")
    if len(value) != 2 * XSRF_TOKEN_SIZE:
        raise ValueError("value isn't %d bytes long: %d"
                         % (2 * XSRF_TOKEN_SIZE, len(value)))
    salt, salted_token = value[:XSRF_TOKEN_SIZE], value[XSRF_TOKEN_SIZE:]
    return bytes(s ^ t for s, t in zip(salt, salted_token))


@app.before_request
def prepare_context():
    expected_xsrf_token = request.cookies.get("_xsrf", None)
    if expected_xsrf_token is not None:
        try:
            expected_xsrf_token = unsalt_xsrf_token(expected_xsrf_token)
        except (TypeError, ValueError) as err:
            logger.warning("Bad XSRF token in cookie: %s", err)
            expected_xsrf_token = None

    if request.method == "POST":
        if expected_xsrf_token is None:
            logger.warning("No XSRF token in cookie.")
            raise HTTPException(403)
        received_xsrf_token = request.form.get("_xsrf", None)
        if received_xsrf_token is None:
            logger.warning("No XSRF token in form field.")
            raise HTTPException(403)
        try:
            received_xsrf_token = unsalt_xsrf_token(received_xsrf_token)
        except (TypeError, ValueError) as err:
            logger.warning("Bad XSRF token in form field: %s", err)
            raise HTTPException(403)
        if not compare_digest(expected_xsrf_token, received_xsrf_token):
            logger.warning("XSRF tokens don't match")
            raise HTTPException(403)

    if expected_xsrf_token is None:
        expected_xsrf_token = generate_xsrf_token()

    session["_xsrf"] = salt_xsrf_token(expected_xsrf_token)
    g.xsrf_form_html = ('<input type="hidden" name="_xsrf" value="%s"/>'
                        % escape(salt_xsrf_token(expected_xsrf_token)))

    g.timestamp = make_datetime()
    g.session = Session()
    # FIXME could even go to app
    g.printing_enabled = config.printer is not None

    # The list of interface translations the user can choose from.
    g.available_translations = current_app.service.translations
    # The translation that best matches the user's system settings
    # (as reflected by the browser in the HTTP request's
    # Accept-Language header).
    g.automatic_translation = DEFAULT_TRANSLATION
    # The translation that the user specifically manually picked.
    g.cookie_translation = None
    # The translation that we are going to use.
    g.translation = DEFAULT_TRANSLATION
    g._ = g.translation.gettext
    g.n_ = g.translation.ngettext


@app.after_request
def clean_up(response):
    if hasattr(g, "session"):
        g.session.rollback()

    return response


def templated(template):
    def decorator(f):
        @wraps(f)
        def wrapped_f(*args, **kwargs):
            ctx = f(*args, **kwargs)
            if ctx is None:
                ctx = {}
            elif not isinstance(ctx, dict):
                return ctx
            return render_template(template, **ctx)
        return wrapped_f
    return decorator


@app.errorhandler(HTTPException)
def page_not_found(error):
    code = error.code if isinstance(error, HTTPException) else 500
    # FIXME return 200 always?
    return "Error %d" % code, code


@app.context_processor
def render_params():
    ret = dict()
    ret["now"] = g.timestamp
    ret["tzinfo"] = local_tzinfo
    ret["utc"] = utc_tzinfo

    ret["available_translations"] = g.available_translations
    ret["cookie_translation"] = g.cookie_translation
    ret["automatic_translation"] = g.automatic_translation
    ret["translation"] = g.translation
    ret["gettext"] = g._
    ret["ngettext"] = g.n_

    ret["xsrf_form_html"] = g.xsrf_form_html
    ret["printing_enabled"] = g.printing_enabled

    return ret


@templated("contest_list.html")
def contest_list_handler():
    # We need this to be computed for each request because we want to be
    # able to import new contests without having to restart CWS.
    contest_list = dict()
    for contest in g.session.query(Contest).all():
        contest_list[contest.name] = contest
    return {"contest_list": contest_list}


# The following prefixes are handled by WSGI middlewares:
# * /static, defined in cms/io/web_service.py
# * /stl, defined in cms/server/contest/server.py


def fetch(digest, mimetype, filename):
    return base_fetch(digest, filename, mimetype,
                      current_app.service.file_cacher, request.environ)
