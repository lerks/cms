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
from functools import wraps, partial

from flask import Flask, current_app, send_from_directory
from flask import g
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


@app.before_request
def prepare_context():
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
    g.session.rollback()


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
    return 'This page does not exist', 404


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

    # ret["xsrf_form_html"] = xsrf_form_html()
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
