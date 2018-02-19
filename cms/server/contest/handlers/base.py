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
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa
from six import iterkeys

import logging
import os
import traceback
from functools import wraps

import tornado.web
from werkzeug.datastructures import LanguageAccept
from werkzeug.exceptions import HTTPException
from werkzeug.http import parse_accept_header
from jinja2 import TemplateNotFound
from flask import Blueprint,  abort
from flask import Flask, current_app
from flask import g, redirect, url_for
from flask import request, render_template

from cms import TOKEN_MODE_MIXED, config
from cms.db import Contest, ScopedSession
from cms.locale import DEFAULT_TRANSLATION, choose_language_code
from cms.server import CommonRequestHandler, compute_actual_phase
from cms.server.contest.authentication import get_current_user
from cmscommon.datetime import utc as utc_tzinfo, local as local_tzinfo, \
    get_timezone, make_datetime
from cms.server.contest.handlers import app, contest_bp
from cms.server import CommonRequestHandler
from cmscommon.datetime import utc as utc_tzinfo


logger = logging.getLogger(__name__)


@contest_bp.route('/<page>')
def show(page):
    try:
        return render_template('pages/%s.html' % page)
    except TemplateNotFound:
        abort(404)


@contest_bp.url_defaults
def add_contest_name(endpoint, values):
    values.setdefault('contest', g.contest.name)


@contest_bp.url_value_preprocessor
def pull_contest_name(endpoint, values):
    with ScopedSession() as session:
        if hasattr(current_app, "contest_id"):
            g.contest = Contest.get_from_id(current_app.contest_id, session)
        else:
            g.contest = Contest.by_name(values.pop('contest'))


@app.teardown_appcontext
def shutdown_session(exception=None):
    with ScopedSession() as session:
        session.remove()


@app.before_request
def inject_timestamp():
    g.timestamp = make_datetime()


def authentication_required(refresh_cookie=True):
    def decorator(f):
        @wraps(f)
        def wrapped_f(*args, **kwargs):
            with ScopedSession() as session:
                participation, cookie = get_current_user(
                    session, g.contest, g.timestamp, ip_address, cookie)

            if cookie is None:
                reset cookie
            elif refresh_cookie:
                set cookie

            if participation is None:
                return redirect(url_for('contest.login', next=request.url))

            g.participation = participation

            return f(*args, **kwargs)

        return wrapped_f

    return decorator


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
    ret["url"] = g.url
    ret["available_translations"] = g.available_translations
    ret["cookie_translation"] = g.cookie_translation
    ret["automatic_translation"] = g.automatic_translation
    ret["translation"] = g.translation
    ret["gettext"] = g._
    ret["ngettext"] = g.n_
    ret["xsrf_form_html"] = xsrf_form_html()
    return ret


@contest_bp.context_processor
def contest_render_params():
    ret = dict()

    ret["contest"] = g.contest

    ret["phase"] = g.contest.phase(g.timestamp)

    ret["printing_enabled"] = (config.printer is not None)
    ret["questions_enabled"] = g.contest.allow_questions
    ret["testing_enabled"] = g.contest.allow_user_tests

    if g.participation is not None:
        ret["current_user"] = g.participation
        g.participation = g.participation

        res = compute_actual_phase(
            self.timestamp, g.contest.start, g.contest.stop,
            g.contest.analysis_start if g.contest.analysis_enabled
            else None,
            g.contest.analysis_stop if g.contest.analysis_enabled
            else None,
            g.contest.per_user_time, g.participation.starting_time,
            g.participation.delay_time, g.participation.extra_time)

        ret["actual_phase"], ret["current_phase_begin"], \
            ret["current_phase_end"], ret["valid_phase_begin"], \
            ret["valid_phase_end"] = res

        if ret["actual_phase"] == 0:
            ret["phase"] = 0

        # set the timezone used to format timestamps
        ret["timezone"] = get_timezone(g.user, g.contest)

    # some information about token configuration
    ret["tokens_contest"] = g.contest.token_mode

    t_tokens = set(t.token_mode for t in g.contest.tasks)
    if len(t_tokens) == 1:
        ret["tokens_tasks"] = next(iter(t_tokens))
    else:
        ret["tokens_tasks"] = TOKEN_MODE_MIXED

    return ret



class BaseHandler(CommonRequestHandler):
    """Base RequestHandler for this application.

    This will also handle the contest list on the homepage.

    """

    def __init__(self, *args, **kwargs):
        super(BaseHandler, self).__init__(*args, **kwargs)
        # The list of interface translations the user can choose from.
        self.available_translations = self.service.translations
        # The translation that best matches the user's system settings
        # (as reflected by the browser in the HTTP request's
        # Accept-Language header).
        self.automatic_translation = DEFAULT_TRANSLATION
        # The translation that the user specifically manually picked.
        self.cookie_translation = None
        # The translation that we are going to use.
        self.translation = DEFAULT_TRANSLATION
        self._ = self.translation.gettext
        self.n_ = self.translation.ngettext

    def prepare(self):
        """This method is executed at the beginning of each request.

        """
        super(BaseHandler, self).prepare()
        self.setup_locale()

    def setup_locale(self):
        lang_codes = list(iterkeys(self.available_translations))

        browser_langs = parse_accept_header(
            self.request.headers.get("Accept-Language", ""),
            LanguageAccept).values()
        automatic_lang = choose_language_code(browser_langs, lang_codes)
        if automatic_lang is None:
            automatic_lang = lang_codes[0]
        self.automatic_translation = \
            self.available_translations[automatic_lang]

        cookie_lang = self.get_cookie("language", None)
        if cookie_lang is not None:
            chosen_lang = \
                choose_language_code([cookie_lang, automatic_lang], lang_codes)
            if chosen_lang == cookie_lang:
                self.cookie_translation = \
                    self.available_translations[cookie_lang]
        else:
            chosen_lang = automatic_lang
        self.translation = self.available_translations[chosen_lang]

        self._ = self.translation.gettext
        self.n_ = self.translation.ngettext

        self.set_header("Content-Language", chosen_lang)

    def write_error(self, status_code, **kwargs):
        if "exc_info" in kwargs and \
                kwargs["exc_info"][0] != tornado.web.HTTPError:
            exc_info = kwargs["exc_info"]
            logger.error(
                "Uncaught exception (%r) while processing a request: %s",
                exc_info[1], ''.join(traceback.format_exception(*exc_info)))

        # We assume that if r_params is defined then we have at least
        # the data we need to display a basic template with the error
        # information. If r_params is not defined (i.e. something went
        # *really* bad) we simply return a basic textual error notice.
        if self.r_params is not None:
            self.render("error.html", status_code=status_code, **self.r_params)
        else:
            self.write("A critical error has occurred :-(")
            self.finish()


# TODO actually should be inserted dynamically if multi-contest
@app.route("/", methods=["GET"])
@templated("contest_list.html")
def contest_list_handler(self):
    # We need this to be computed for each request because we want to be
    # able to import new contests without having to restart CWS.
    contest_list = dict()
    for contest in self.sql_session.query(Contest).all():
        contest_list[contest.name] = contest
    return {"contest_list": contest_list}
